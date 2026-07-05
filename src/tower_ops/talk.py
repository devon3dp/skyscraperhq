"""TALK button backend — accepts mic transcript and forwards to kernel chat."""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG_PATH = ROOT / "logs/tower_ops/talk_events.jsonl"


def _now(): return datetime.now(timezone.utc).isoformat()


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now()); rec["execution_allowed"] = False
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def talk_transcript(payload):
    """Send a microphone transcript to the kernel chat sidecar."""
    payload = payload or {}
    transcript = (payload.get("transcript") or "").strip()
    if not transcript:
        return {"ok": False, "error": "transcript_required"}
    _append_log({"event": "talk_transcript", "transcript_length": len(transcript)})
    # Forward to kernel chat through the existing dashboard proxy on this port.
    import urllib.request, urllib.error
    try:
        data = json.dumps({"message": transcript}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8765/api/kernel_chat",
                                       data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=90) as resp:
            kr = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200]})
    return stamp_safe({
        "ok": True, "ts": _now(),
        "transcript": transcript[:280],
        "reply": (kr or {}).get("reply"),
        "bridge": (kr or {}).get("bridge"),
        "execution_allowed": False,
    })


def speak(payload):
    """Server-side endpoint — actual speech happens in the browser. Returns instruction only."""
    return stamp_safe({"ok": True, "ts": _now(),
                        "method": "browser_web_speech_synthesis",
                        "execution_allowed": False,
                        "instruction": (payload or {}).get("text") or ""})


def floor_narration(payload):
    payload = payload or {}
    floor = payload.get("floor")
    return stamp_safe({"ok": True, "ts": _now(),
                        "floor": floor,
                        "narration": f"Floor {floor} live update.",
                        "method": "browser_web_speech_synthesis",
                        "execution_allowed": False})
