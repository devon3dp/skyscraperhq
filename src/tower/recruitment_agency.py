#!/usr/bin/env python3
"""
QSB Tower V1.3 — Worker Recruitment Agency V1

Phase: QSB_TOWER_PENTHOUSE_CHAT_SOUND_RECRUITMENT_V1

The Recruitment Agency owns the real, named worker roster used by the
QSB cockpit. Workers here have real lifecycle stages, real capability
cards, real heartbeats, and real OpenClaw-readiness badges — but every
single execution / live-trading / provider / dispatch / OpenClaw flag
stays false. The Agency NEVER toggles execution on, no matter what
input it receives.

Hard contract (enforced in code, not config):
  - `openclaw_review` marks a worker `openclaw_ready=true` and bumps the
    stage to `ready_for_openclaw_review`. It does NOT set
    openclaw_execution_enabled=true. Ever.
  - `recruit / assign / retire / openclaw_review` are local-only POST
    routes proxied through the existing dashboard server on port 8765.
    No new ports, no new sidecars.
  - Heartbeats are stamped lazily on every read — no daemon process.
  - The Agency lives in `data/registries/recruitment_workers.json`
    (state) and `data/logs/recruitment_agency.jsonl` (audit log).
  - No AirLLM autoloop wiring. No AirLLM trading wiring.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import threading
import uuid


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "data/registries/recruitment_workers.json"
LOG_PATH   = ROOT / "data/logs/recruitment_agency.jsonl"
POLICY_PATH = ROOT / "data/registries/recruitment_agency_policy.json"

# Locks that the Recruitment Agency must always stamp false on every
# published record. Adding these new keys also surfaces them in
# /api/unified's lock matrix so Floor 30 Risk sees them.
LOCKED_FALSE = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "binance_order_execution_enabled": False,
    "binance_live_trading_enabled": False,
    "stock_order_execution_enabled": False,
    "stock_live_trading_enabled": False,
    "stock_paper_order_execution_enabled": False,
    "cross_market_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False,
    # New lock keys introduced by this phase
    "recruitment_openclaw_execution_enabled": False,
    "recruited_worker_live_execution_enabled": False,
    "recruited_worker_provider_access_enabled": False,
    "recruited_worker_autonomous_dispatch_enabled": False,
}

VALID_STAGES = (
    "candidate", "interviewed", "onboarded", "probation",
    "active_read_only", "active_advisory",
    "ready_for_openclaw_review", "rejected",
)

# Initial seed roster — REAL workers, not sandbox placeholders.
# Each entry has full lifecycle metadata. The cockpit reads these via the
# dashboard /api/recruitment/* routes.
SEED_ROSTER = [
    # ── Trading / market workers ────────────────────────────────────────
    {"id": "fx_market_scout",          "display_name": "FX Market Scout",
     "role": "Reads OANDA practice pricing + identifies quote status.",
     "floor_assignment": "floor_41", "desk_assignment": "FX Pricing Desk",
     "capabilities": ["read_oanda_practice", "quote_status", "spread_observation"],
     "stage": "active_read_only", "openclaw_ready": False,
     "team": "trading_fx"},
    {"id": "fx_spread_watcher",        "display_name": "FX Spread Watcher",
     "role": "Measures FX bid/ask spreads + quote-quality conditions.",
     "floor_assignment": "floor_41", "desk_assignment": "FX Pricing Desk",
     "capabilities": ["spread_measurement", "quote_quality"],
     "stage": "active_read_only", "openclaw_ready": False,
     "team": "trading_fx"},
    {"id": "crypto_market_scout",      "display_name": "Crypto Market Scout",
     "role": "Reads Binance testnet public market data.",
     "floor_assignment": "floor_42", "desk_assignment": "Testnet Market Feed",
     "capabilities": ["read_binance_testnet", "public_market_data"],
     "stage": "active_read_only", "openclaw_ready": False,
     "team": "trading_crypto"},
    {"id": "crypto_spread_watcher",    "display_name": "Crypto Spread Watcher",
     "role": "Measures crypto bid/ask spreads on Binance testnet.",
     "floor_assignment": "floor_42", "desk_assignment": "Testnet Market Feed",
     "capabilities": ["spread_measurement"],
     "stage": "active_read_only", "openclaw_ready": False,
     "team": "trading_crypto"},
    {"id": "equity_market_scout",      "display_name": "Equity Market Scout",
     "role": "Reads US equities quotes/bars via Floor 43 gateway.",
     "floor_assignment": "floor_43", "desk_assignment": "Market Data Desk",
     "capabilities": ["read_alpaca_paper", "stock_quote_status"],
     "stage": "active_read_only", "openclaw_ready": False,
     "team": "trading_equities"},
    {"id": "cross_market_correlation", "display_name": "Cross-Market Correlation Clerk",
     "role": "Reads OANDA/Binance/Stock registries + builds correlation pairs.",
     "floor_assignment": "floor_37", "desk_assignment": "Cross-Market Inputs",
     "capabilities": ["read_registries", "correlation_pairing"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "strategy"},
    {"id": "paper_strategy_analyst",   "display_name": "Paper Strategy Analyst",
     "role": "Synthesizes paper-only signals; never places orders.",
     "floor_assignment": "floor_37", "desk_assignment": "Paper Signals",
     "capabilities": ["paper_signal_synthesis", "advisory_only"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "strategy"},
    {"id": "risk_sentinel",            "display_name": "Risk Sentinel",
     "role": "Verifies all execution locks remain closed every tick.",
     "floor_assignment": "floor_30", "desk_assignment": "Lock Matrix",
     "capabilities": ["lock_audit", "risk_alerting"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "risk"},
    {"id": "ledger_clerk",             "display_name": "Ledger Clerk",
     "role": "Persists paper observations into the audit ledger.",
     "floor_assignment": "floor_31", "desk_assignment": "Ledger Counter",
     "capabilities": ["append_only_ledger", "paper_audit_trail"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "audit"},
    {"id": "kernel_commentary_runner", "display_name": "Kernel Commentary Runner",
     "role": "Carries kernel-review packets toward the Penthouse.",
     "floor_assignment": "floor_53", "desk_assignment": "Kernel Review Route",
     "capabilities": ["kernel_review_packet", "advisory_only"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "command"},

    # ── OpenClaw-readiness workers (advisory only — execution locked) ──
    {"id": "openclaw_lift_observer",   "display_name": "OpenClaw Lift Observer",
     "role": "Observes lift packet patterns. Sees only — never executes.",
     "floor_assignment": "floor_38", "desk_assignment": "OpenClaw Visual Sandbox",
     "capabilities": ["lift_packet_observation"],
     "stage": "ready_for_openclaw_review", "openclaw_ready": True,
     "team": "openclaw_advisory"},
    {"id": "openclaw_risk_guard",      "display_name": "OpenClaw Risk Guard",
     "role": "Reviews OpenClaw recommendations for safety pre-execution.",
     "floor_assignment": "floor_30", "desk_assignment": "Inbound from Sandbox",
     "capabilities": ["openclaw_recommendation_review"],
     "stage": "ready_for_openclaw_review", "openclaw_ready": True,
     "team": "openclaw_advisory"},
    {"id": "openclaw_visual_clerk",    "display_name": "OpenClaw Visual Clerk",
     "role": "Logs OpenClaw visual sandbox ticks for audit.",
     "floor_assignment": "floor_38", "desk_assignment": "OpenClaw Visual Sandbox",
     "capabilities": ["openclaw_sandbox_logging"],
     "stage": "active_read_only", "openclaw_ready": True,
     "team": "openclaw_advisory"},
    {"id": "openclaw_task_intake",     "display_name": "OpenClaw Task Intake Clerk",
     "role": "Receives candidate tasks. Routes to Risk before any execution.",
     "floor_assignment": "floor_38", "desk_assignment": "Reception Desk",
     "capabilities": ["task_intake", "risk_routing"],
     "stage": "onboarded", "openclaw_ready": False,
     "team": "openclaw_advisory"},
    {"id": "openclaw_readiness_aud",   "display_name": "OpenClaw Readiness Auditor",
     "role": "Verifies a worker meets OpenClaw readiness criteria.",
     "floor_assignment": "floor_38", "desk_assignment": "OpenClaw Review Gate",
     "capabilities": ["readiness_audit"],
     "stage": "active_advisory", "openclaw_ready": True,
     "team": "openclaw_advisory"},

    # ── Media / speech workers (homes on real Floor 14 / 15) ────────────
    {"id": "speech_route_monitor",     "display_name": "Speech Route Monitor",
     "role": "Watches Floor 15 Speech & Audio sidecar liveness.",
     "floor_assignment": "floor_15", "desk_assignment": "Speech Routing",
     "capabilities": ["speech_route_health"],
     "stage": "candidate", "openclaw_ready": False,
     "team": "speech_media"},
    {"id": "tts_output_clerk",         "display_name": "TTS Output Clerk",
     "role": "Routes kernel replies to browser TTS / local speech sink.",
     "floor_assignment": "floor_15", "desk_assignment": "TTS Output",
     "capabilities": ["browser_web_speech", "tts_dispatch"],
     "stage": "candidate", "openclaw_ready": False,
     "team": "speech_media"},
    {"id": "stt_intake_clerk",         "display_name": "STT Intake Clerk",
     "role": "Accepts microphone transcripts from the dashboard.",
     "floor_assignment": "floor_15", "desk_assignment": "STT Intake",
     "capabilities": ["browser_web_speech_recognition"],
     "stage": "candidate", "openclaw_ready": False,
     "team": "speech_media"},
    {"id": "media_floor_liaison",      "display_name": "Media Floor Liaison",
     "role": "Coordinates between Floor 14 Media and Floor 15 Speech.",
     "floor_assignment": "floor_14", "desk_assignment": "Media Routing",
     "capabilities": ["media_coordination"],
     "stage": "candidate", "openclaw_ready": False,
     "team": "speech_media"},

    # ── AirLLM advisory workers ────────────────────────────────────────
    {"id": "airllm_model_scout",       "display_name": "AirLLM Model Scout",
     "role": "Reads AirLLM chamber registry. Never invokes the model.",
     "floor_assignment": "floor_23", "desk_assignment": "Big Model Chamber",
     "capabilities": ["read_airllm_registry"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "airllm_advisory"},
    {"id": "big_model_prompt_clerk",   "display_name": "Big Model Prompt Clerk",
     "role": "Future manual 'Ask Big Air Model' lane. Disabled until reviewed.",
     "floor_assignment": "floor_23", "desk_assignment": "Future Manual Ask Lane",
     "capabilities": ["prompt_drafting"],
     "stage": "candidate", "openclaw_ready": False,
     "team": "airllm_advisory"},
    {"id": "advisory_output_auditor",  "display_name": "Advisory Output Auditor",
     "role": "Audits any advisory output before it reaches Ledger.",
     "floor_assignment": "floor_31", "desk_assignment": "Advisory Audit",
     "capabilities": ["advisory_audit"],
     "stage": "active_advisory", "openclaw_ready": False,
     "team": "airllm_advisory"},
]


# A process-wide lock around the state file (single dashboard process).
_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _baseline_state():
    return {
        "registry": "qsb_worker_recruitment_agency_v1",
        "phase": "QSB_TOWER_PENTHOUSE_CHAT_SOUND_RECRUITMENT_V1",
        "agency_floor": "floor_38",
        "agency_name": "Worker Recruitment Agency",
        "created_ts": _now(),
        "updated_ts": _now(),
        "locks": dict(LOCKED_FALSE),
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
        "advisory_only": True,
        "workers": [_normalize_worker(w) for w in SEED_ROSTER],
        "lifecycle_stages": list(VALID_STAGES),
    }


def _normalize_worker(w):
    out = dict(w)
    out.setdefault("openclaw_execution_enabled", False)
    out.setdefault("provider_access_enabled",    False)
    out.setdefault("autonomous_dispatch_enabled", False)
    out.setdefault("openclaw_ready",  bool(out.get("openclaw_ready", False)))
    out.setdefault("stage",           "candidate")
    out.setdefault("health",          "healthy")
    out.setdefault("heartbeat_ts",    _now())
    out.setdefault("current_task",    "idle")
    out.setdefault("last_packet",     None)
    out.setdefault("audit_count",     0)
    out.setdefault("training_status", "complete" if out.get("stage") in
                                       ("active_read_only", "active_advisory",
                                        "ready_for_openclaw_review") else "pending")
    out.setdefault("notes",           "")
    # Universal forbidden actions — same for every worker, no exceptions.
    out.setdefault("forbidden_actions", [
        "live_trading", "order_execution", "practice_order_execution",
        "openclaw_execution", "autonomous_dispatch",
        "direct_provider_access", "external_provider_execution",
        "live_dispatch",
    ])
    out.setdefault("allowed_actions", _allowed_actions_for_stage(out.get("stage")))
    return out


def _allowed_actions_for_stage(stage):
    base = ["read_registries", "advisory_packet_emit", "audit_log_write"]
    if stage in ("candidate",):                       return ["heartbeat_only"]
    if stage in ("interviewed",):                     return ["heartbeat_only", "self_describe"]
    if stage in ("onboarded",):                       return base + ["training_attend"]
    if stage in ("probation",):                       return base + ["observation_only"]
    if stage in ("active_read_only",):                return base + ["observation_only"]
    if stage in ("active_advisory",):                 return base + ["observation_only", "advisory_synthesis"]
    if stage in ("ready_for_openclaw_review",):       return base + ["observation_only", "advisory_synthesis", "openclaw_review_packet"]
    if stage in ("rejected",):                        return []
    return ["heartbeat_only"]


def _read_state():
    if not STATE_PATH.exists():
        _ensure_dirs()
        state = _baseline_state()
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        # Corrupted — rebuild from baseline (audit logs preserved separately)
        state = _baseline_state()
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state


def _write_state(state):
    state["updated_ts"] = _now()
    state["locks"] = dict(LOCKED_FALSE)
    state["execution_allowed"] = False
    state["paper_only"] = True
    state["not_financial_advice"] = True
    state["advisory_only"] = True
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_log(record):
    _ensure_dirs()
    record = dict(record)
    record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    record.setdefault("paper_only", True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _stamp_heartbeats(state):
    """Lazy heartbeat update — runs on every read.

    Pretty simple: bumps heartbeat_ts on every worker that isn't rejected,
    and assigns a short live `current_task` description derived from stage.
    No real worker process is running — this is honest "registry liveness"
    not "live execution". Every read is a heartbeat tick.
    """
    now = _now()
    audit_bump = False
    for w in state.get("workers") or []:
        if w.get("stage") == "rejected":
            w["health"] = "retired"
            continue
        w["heartbeat_ts"] = now
        if not w.get("current_task") or w.get("current_task") == "idle":
            w["current_task"] = _task_for_stage(w.get("stage"))
        w["audit_count"] = (w.get("audit_count") or 0) + 1
        audit_bump = True
    state["updated_ts"] = now
    state["last_heartbeat_ts"] = now
    return audit_bump


def _task_for_stage(stage):
    return {
        "candidate":                 "awaiting_interview",
        "interviewed":               "awaiting_onboarding",
        "onboarded":                 "training",
        "probation":                 "observation_only",
        "active_read_only":          "reading_registries",
        "active_advisory":           "advisory_synthesis",
        "ready_for_openclaw_review": "awaiting_openclaw_review",
        "rejected":                  "retired",
    }.get(stage, "idle")


# ── Public API ─────────────────────────────────────────────────────────
def status():
    with _LOCK:
        state = _read_state()
        _stamp_heartbeats(state)
        _write_state(state)
        workers = state.get("workers") or []
        by_stage = {}
        for w in workers:
            by_stage[w.get("stage", "candidate")] = by_stage.get(w.get("stage", "candidate"), 0) + 1
        openclaw_ready = [w["id"] for w in workers if w.get("openclaw_ready") and w.get("stage") != "rejected"]
        return {
            "ok": True,
            "ts": _now(),
            "phase": state.get("phase"),
            "agency_name": state.get("agency_name"),
            "agency_floor": state.get("agency_floor"),
            "total_workers": len(workers),
            "active_advisory":              by_stage.get("active_advisory", 0),
            "active_read_only":             by_stage.get("active_read_only", 0),
            "ready_for_openclaw_review":    by_stage.get("ready_for_openclaw_review", 0),
            "candidates":                   by_stage.get("candidate", 0),
            "rejected":                     by_stage.get("rejected", 0),
            "by_stage": by_stage,
            "openclaw_ready_count":         len(openclaw_ready),
            "openclaw_ready_ids":           openclaw_ready,
            "locks": dict(LOCKED_FALSE),
            "execution_allowed": False,
            "paper_only": True,
            "not_financial_advice": True,
            "advisory_only": True,
            "last_heartbeat_ts": state.get("last_heartbeat_ts"),
        }


def workers():
    with _LOCK:
        state = _read_state()
        _stamp_heartbeats(state)
        _write_state(state)
        return {
            "ok": True,
            "ts": _now(),
            "phase": state.get("phase"),
            "agency_name": state.get("agency_name"),
            "agency_floor": state.get("agency_floor"),
            "workers": state.get("workers") or [],
            "lifecycle_stages": list(VALID_STAGES),
            "locks": dict(LOCKED_FALSE),
            "execution_allowed": False,
            "paper_only": True,
            "advisory_only": True,
        }


def recruit(payload):
    payload = payload or {}
    display_name = (payload.get("display_name") or "").strip()
    role         = (payload.get("role") or "").strip()
    floor        = payload.get("floor_assignment") or "floor_38"
    desk         = payload.get("desk_assignment") or "Reception Desk"
    capabilities = payload.get("capabilities") or []
    team         = payload.get("team") or "general"
    if not display_name:
        return {"ok": False, "error": "display_name_required"}
    wid = "rec_" + uuid.uuid4().hex[:10]
    new_worker = _normalize_worker({
        "id": wid,
        "display_name": display_name,
        "role": role or "Recruited worker.",
        "floor_assignment": floor,
        "desk_assignment":  desk,
        "capabilities":     list(capabilities),
        "team":             team,
        "stage":            "candidate",
        "openclaw_ready":   False,
        "notes": payload.get("notes") or "",
    })
    with _LOCK:
        state = _read_state()
        state["workers"].append(new_worker)
        _stamp_heartbeats(state)
        _write_state(state)
        _append_log({"event": "recruit", "worker_id": wid, "display_name": display_name})
    return {"ok": True, "worker": new_worker, "execution_allowed": False}


def assign(payload):
    payload = payload or {}
    wid    = payload.get("worker_id")
    floor  = payload.get("floor_assignment")
    desk   = payload.get("desk_assignment")
    stage  = payload.get("stage")
    if stage and stage not in VALID_STAGES:
        return {"ok": False, "error": "invalid_stage", "valid_stages": list(VALID_STAGES)}
    with _LOCK:
        state = _read_state()
        for w in state["workers"]:
            if w.get("id") == wid:
                if floor: w["floor_assignment"] = floor
                if desk:  w["desk_assignment"]  = desk
                if stage:
                    w["stage"] = stage
                    w["allowed_actions"] = _allowed_actions_for_stage(stage)
                    w["current_task"]    = _task_for_stage(stage)
                # Locks NEVER change here.
                w["openclaw_execution_enabled"]   = False
                w["provider_access_enabled"]      = False
                w["autonomous_dispatch_enabled"]  = False
                _stamp_heartbeats(state)
                _write_state(state)
                _append_log({"event": "assign", "worker_id": wid,
                             "floor_assignment": floor, "desk_assignment": desk, "stage": stage})
                return {"ok": True, "worker": w, "execution_allowed": False}
        return {"ok": False, "error": "worker_not_found", "worker_id": wid}


def retire(payload):
    payload = payload or {}
    wid = payload.get("worker_id")
    with _LOCK:
        state = _read_state()
        for w in state["workers"]:
            if w.get("id") == wid:
                w["stage"] = "rejected"
                w["health"] = "retired"
                w["current_task"] = "retired"
                w["allowed_actions"] = []
                w["openclaw_ready"] = False
                w["openclaw_execution_enabled"]   = False
                w["provider_access_enabled"]      = False
                w["autonomous_dispatch_enabled"]  = False
                _stamp_heartbeats(state)
                _write_state(state)
                _append_log({"event": "retire", "worker_id": wid})
                return {"ok": True, "worker": w, "execution_allowed": False}
        return {"ok": False, "error": "worker_not_found", "worker_id": wid}


def openclaw_review(payload):
    """Marks a worker openclaw_ready=true. Does NOT enable execution."""
    payload = payload or {}
    wid = payload.get("worker_id")
    with _LOCK:
        state = _read_state()
        for w in state["workers"]:
            if w.get("id") == wid:
                w["openclaw_ready"] = True
                w["stage"] = "ready_for_openclaw_review"
                w["allowed_actions"] = _allowed_actions_for_stage("ready_for_openclaw_review")
                w["current_task"] = "awaiting_openclaw_review"
                # Lock guarantees, no matter what.
                w["openclaw_execution_enabled"]   = False
                w["provider_access_enabled"]      = False
                w["autonomous_dispatch_enabled"]  = False
                _stamp_heartbeats(state)
                _write_state(state)
                _append_log({"event": "openclaw_review", "worker_id": wid,
                             "openclaw_ready": True,
                             "openclaw_execution_enabled": False})
                return {"ok": True, "worker": w,
                        "openclaw_ready": True,
                        "openclaw_execution_enabled": False,
                        "execution_allowed": False}
        return {"ok": False, "error": "worker_not_found", "worker_id": wid}


def dashboard():
    return {
        "agency_floor": "floor_38",
        "agency_name": "Worker Recruitment Agency",
        "status_endpoint":          "/api/recruitment/status",
        "workers_endpoint":         "/api/recruitment/workers",
        "recruit_endpoint":         "/api/recruitment/recruit",
        "assign_endpoint":          "/api/recruitment/assign",
        "retire_endpoint":          "/api/recruitment/retire",
        "openclaw_review_endpoint": "/api/recruitment/openclaw_review",
        "execution_allowed": False,
        "paper_only": True,
    }


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
