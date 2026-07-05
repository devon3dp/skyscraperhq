"""Speech & Audio Department V1 — Floor 15 status + diagnostics endpoint."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def status():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "department": "Speech and Audio Department",
        "floor_number": 15, "floor_id": "floor_15",
        "tts_engine": "browser_web_speech_synthesis",
        "stt_engine": "browser_web_speech_recognition",
        "local_sidecar_present": False,
        "external_speech_provider": "none",
        "browser_web_speech_supported_hint": "verified by browser at runtime",
        "speech_to_kernel_route": "browser → /api/kernel_chat → :8766 sidecar",
        "kernel_reply_to_tts_route": "kernel reply → browser SpeechSynthesisUtterance",
        "auto_speak_supported_at_browser": True,
        "mic_browser_permission_required": True,
        "advisory_only": True,
    })


def diagnostics():
    s = status()
    s["notes"] = [
        "Speech is browser-side — install no extra packages.",
        "Mic requires the browser's microphone permission prompt.",
        "If a browser doesn't support Web Speech, text chat still works.",
        "No external speech provider is contacted.",
    ]
    return s
