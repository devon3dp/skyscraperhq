"""Colonel Concierge + Colonel Butler — Penthouse staff."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .safety_contract import LOCKED_FALSE, stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG_PATH = ROOT / "logs/tower_ops/colonel_concierge.jsonl"


def _now(): return datetime.now(timezone.utc).isoformat()


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now()); rec.setdefault("execution_allowed", False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def concierge_summary():
    """Quick summary for the Penthouse concierge card."""
    # Lazy imports to avoid circulars
    from .worker_registry  import status as worker_status
    from .management_chain import status as mgr_status
    from .overseer_registry import status as ov_status
    ws = worker_status(); ms = mgr_status(); os_ = ov_status()
    _append_log({"event": "concierge_summary_read"})
    return stamp_safe({
        "ok": True, "ts": _now(),
        "concierge_status": "on_duty",
        "tower_state": "active_local_only · 0/many locks TRUE · paper-only",
        "worker_count":   ws.get("total_workers"),
        "manager_count":  ms.get("total_managers"),
        "overseer_count": os_.get("total_overseers"),
        "openclaw_ready_count": ws.get("openclaw_ready_count"),
        "active_advisory":      ws.get("active_advisory"),
        "active_read_only":     ws.get("active_read_only"),
        "ready_for_openclaw_review": ws.get("ready_for_openclaw_review"),
        "candidates":           ws.get("candidates"),
        "kernel_chat_route":    "POST /api/kernel_chat",
        "speech_floor": "floor_15", "media_floor": "floor_14",
        "actions": [
            {"label": "Open Kernel Chat",         "target": "penthouse_chat"},
            {"label": "Open Recruitment Agency",  "target_floor": 38},
            {"label": "Open Maintenance",         "target_floor": 33},
            {"label": "Open Security",            "target_floor": 28},
            {"label": "Open IT",                  "target_floor": 35},
            {"label": "Open Research",            "target_floor": 3},
            {"label": "Read Tower Report",        "target": "tower_report"},
            {"label": "Show Alerts",              "target": "alerts"},
        ],
    })


def butler_briefing():
    from .worker_registry  import status as worker_status
    from .maintenance      import status as maint_status
    from .security         import status as sec_status
    from .it_ops           import status as it_status
    from .research_facility import status as res_status
    ws  = worker_status(); m = maint_status(); s = sec_status(); it = it_status(); r = res_status()
    _append_log({"event": "butler_briefing_read"})
    return stamp_safe({
        "ok": True, "ts": _now(),
        "butler_status": "on_duty",
        "briefing": [
            "Kernel core active local only.",
            "All 25+ execution locks TRUE-count: 0 (expected).",
            "OpenClaw execution: OFF · readiness: assessed without execution.",
            "Live trading: OFF · order execution: OFF · autonomous dispatch: OFF.",
            "External providers: OFF · direct provider access: OFF.",
            "Maintenance: {} · Security: {} · IT: {} · Research: {}.".format(
                m.get("overall_status"), s.get("overall_status"),
                it.get("overall_status"), r.get("overall_status")),
            "Total workers: {} ({} advisory, {} read-only, {} candidates).".format(
                ws.get("total_workers"), ws.get("active_advisory"),
                ws.get("active_read_only"), ws.get("candidates")),
            "AirLLM chamber: advisory only — not wired to AutoLoop/trading/OpenClaw.",
            "Speech/Media: Floor 15 + Floor 14 active (browser-only TTS/STT).",
        ],
        "speech_route":  "browser_web_speech",
        "model_lane":    "ollama llama3.2:latest",
        "memory_lane":   "/api/unified + /api/floor_detail",
        "audio_lane":    "floor_15 → SpeechSynthesisUtterance",
        "unread_reports": 0,
        "floors_needing_attention": [],
    })


def status():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "concierge_status": "on_duty",
        "butler_status":    "on_duty",
        "penthouse_floor": "penthouse",
        "floor_number": 55,
    })
