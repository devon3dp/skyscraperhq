#!/usr/bin/env python3
"""
qsb_wren_look.py — Wren's EYES (Bill's-Claude spec #1, 2026-07-18).

Screenshots the screen (or takes an image path) and describes it with the local vision model
qwen2.5vl:7b, so Wren can actually SEE her own builds/UI before claiming 'live'. This is the
biggest anti-fabrication tool: render -> screenshot -> LOOK -> fix (the render-review loop).

Usage:
  qsb_wren_look.py screenshot "<question>"    # grab the screen, then describe/answer
  qsb_wren_look.py image <path> "<question>"  # describe an existing image
"""
import sys, os, json, base64, subprocess, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = "/vaults/ai/cache/tmp/claude-1000/-vaults-nvme0-qsb-tower-v1/6b0db6d7-f9f2-43bc-9167-cd4316472530/scratchpad"
VMODEL = "qwen2.5vl:7b"


def _grab():
    path = os.path.join(SHOT_DIR, "wren_look.png")
    env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/1000", DISPLAY=":0")
    subprocess.run(["scrot", "-o", path], env=env, timeout=15, capture_output=True)
    return path if os.path.exists(path) else None


def _describe(img_path, question):
    if not os.path.exists(img_path):
        return {"ok": False, "error": f"no image at {img_path}"}
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
            data=json.dumps({"model": VMODEL, "prompt": question or "Describe what you see. Be concrete and truthful; if something looks broken or empty, say so.",
                             "images": [b64], "stream": False, "options": {"num_predict": 300}}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
            return {"ok": True, "image": img_path, "model": VMODEL, "description": d.get("response", "").strip()}
    except Exception as e:
        return {"ok": False, "image": img_path, "error": str(e),
                "note": f"vision model {VMODEL} may still be downloading"}


def _vmodel_ready():
    try:
        tags = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5).read())
        return any(m["name"] == VMODEL for m in tags.get("models", []))
    except Exception:
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: screenshot|image|ready", "vmodel_ready": _vmodel_ready()})); sys.exit(2)
    verb = sys.argv[1]
    if verb == "ready":
        print(json.dumps({"vmodel": VMODEL, "ready": _vmodel_ready()})); sys.exit(0)
    if verb == "screenshot":
        img = _grab()
        if not img:
            print(json.dumps({"ok": False, "error": "screenshot failed"})); sys.exit(1)
        print(json.dumps(_describe(img, sys.argv[2] if len(sys.argv) > 2 else ""), indent=2))
    elif verb == "image":
        print(json.dumps(_describe(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""), indent=2))
    else:
        print(json.dumps({"error": "unknown verb"})); sys.exit(2)
