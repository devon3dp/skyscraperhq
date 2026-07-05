#!/usr/bin/env python3
"""qsb_vision_floor.py — F165 Vision Floor.

Ross 2026-06-12: "open up a vision floor for Wren so you can see, put a small
window up in the dashboard". Captures from the Orbbec Astra Pro (described as
RealSense by Ross — same RGB+depth family). Runs person detection via
OpenCV HOG + SVM. Streams MJPEG to the dashboard.

Endpoints (served on http://127.0.0.1:8821):
  GET /                  -> simple HTML viewer (test page)
  GET /api/vision/status -> JSON snapshot { camera_open, detections, fps, ... }
  GET /api/vision/stream -> MJPEG stream with bounding boxes overlaid
  GET /api/vision/snapshot.jpg -> single JPEG frame

Safety:
- Local only, 127.0.0.1 binding.
- No upload, no cloud STT, no recording.
- Tower advisory locks stay TRUE.
"""
from __future__ import annotations

import argparse
import io
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple, List

try:
    import cv2
    import numpy as np
    HAVE_CV = True
except Exception as exc:
    HAVE_CV = False
    CV_ERROR = str(exc)

PORT = 8821


# ── camera + detection ──────────────────────────────────────────────
class VisionState:
    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self.cap = None
        self.lock = threading.Lock()
        self.last_frame = None              # latest JPEG bytes (with bboxes)
        self.last_detections = []           # [(x,y,w,h)]
        self.last_ts = None
        self.fps_window: List[float] = []
        self.running = False
        self.hog = None
        self.thread = None
        self.error = None

    def open(self):
        if not HAVE_CV:
            self.error = f"opencv missing: {CV_ERROR}"
            return False
        self.cap = cv2.VideoCapture(self.device_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.cap.isOpened():
            self.error = f"failed to open /dev/video{self.device_index}"
            self.cap = None
            return False
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        return True

    def start(self):
        if not self.open():
            return False
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    def _loop(self):
        last_tick = time.time()
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            # detect persons every Nth frame to keep cost down
            try:
                rects, _weights = self.hog.detectMultiScale(
                    frame, winStride=(8, 8), padding=(4, 4), scale=1.05)
                detections = [(int(x), int(y), int(w), int(h))
                              for (x, y, w, h) in rects]
            except Exception:
                detections = []
            # Draw bounding boxes + label
            for (x, y, w, h) in detections:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, "person",
                            (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(frame,
                        datetime.now(timezone.utc).strftime("%H:%M:%S"),
                        (5, frame.shape[0] - 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (200, 230, 255), 1, cv2.LINE_AA)
            # Encode JPEG
            ok2, jpg = cv2.imencode(".jpg", frame,
                                     [int(cv2.IMWRITE_JPEG_QUALITY), 78])
            if ok2:
                with self.lock:
                    self.last_frame = jpg.tobytes()
                    self.last_detections = detections
                    self.last_ts = datetime.now(timezone.utc).isoformat()
            now = time.time()
            dt = now - last_tick
            last_tick = now
            self.fps_window.append(dt)
            if len(self.fps_window) > 30:
                self.fps_window.pop(0)

    def fps(self) -> float:
        if not self.fps_window: return 0.0
        return round(1.0 / max(sum(self.fps_window) / len(self.fps_window), 1e-6), 1)


STATE = VisionState()


# ── HTTP ────────────────────────────────────────────────────────────
VIEWER_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>F165 Vision Floor</title>
<style>
  body{background:#06080f;color:#dfeaff;font:14px/1.4 system-ui;margin:0;padding:20px}
  h1{font-weight:600;letter-spacing:-.4px}
  .frame{display:inline-block;border:1px solid #2a3a55;border-radius:10px;overflow:hidden;background:#0a1428}
  img{display:block}
  .meta{margin-top:12px;color:#90a4cf;font-size:12px;font-variant-numeric:tabular-nums}
</style></head>
<body>
  <h1>Floor 165 &middot; The Vision Room &mdash; what the tower sees right now</h1>
  <div class="frame"><img src="/api/vision/stream" alt="live"></div>
  <div class="meta">advisory only · no recording · 127.0.0.1 only</div>
</body></html>
""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        return  # silence default access log

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(VIEWER_HTML)))
            self.end_headers()
            self.wfile.write(VIEWER_HTML)
            return
        if self.path == "/api/vision/status":
            with STATE.lock:
                payload = {
                    "ok": True,
                    "camera_open": STATE.cap is not None and STATE.cap.isOpened(),
                    "running": STATE.running,
                    "error": STATE.error,
                    "device_index": STATE.device_index,
                    "last_frame_ts": STATE.last_ts,
                    "detections": [
                        {"x": x, "y": y, "w": w, "h": h}
                        for (x, y, w, h) in STATE.last_detections
                    ],
                    "person_count": len(STATE.last_detections),
                    "fps": STATE.fps(),
                    "advisory_only": True,
                    "no_recording": True,
                    "execution_allowed": False,
                }
            return self._json(payload)
        if self.path == "/api/vision/snapshot.jpg":
            with STATE.lock:
                jpg = STATE.last_frame
            if not jpg:
                return self._json({"ok": False, "error": "no frame yet"}, 503)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(jpg)
            return
        if self.path == "/api/vision/stream":
            self.send_response(200)
            self.send_header("Content-Type",
                              "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while STATE.running:
                    with STATE.lock:
                        jpg = STATE.last_frame
                    if jpg:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(jpg)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    time.sleep(1 / 24.0)
            except (BrokenPipeError, ConnectionResetError):
                return
            return
        self._json({"ok": False, "error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--device", type=int, default=0)
    args = ap.parse_args()
    STATE.device_index = args.device
    if not STATE.start():
        print(f"[vision] failed to start: {STATE.error}")
        # Still serve so /api/vision/status reports the error
    print(f"[vision] F165 vision floor on http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
