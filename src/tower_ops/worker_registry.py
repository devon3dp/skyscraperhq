"""Real-worker registry for the QSB Tower.

Persistent state at `state/tower_ops/workers.json`. Workers are seeded the
first time the module is imported. Every read lazily stamps fresh heartbeats
and bumps audit counts. NEVER toggles execution flags.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import threading
import uuid

from .safety_contract import LOCKED_FALSE, stamp_safe
from .org_schema      import FLOOR_TO_DEPARTMENT, zone_for_floor


ROOT       = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/workers.json"
LOG_PATH   = ROOT / "logs/tower_ops/worker_events.jsonl"


VALID_STAGES = (
    "candidate", "interviewed", "onboarded", "probation",
    "active_read_only", "active_advisory",
    "ready_for_openclaw_review", "rejected",
)


# ── Real seed roster — 90 workers spread across the tower ──────────────
# Each entry: (display_name, role, floor, desk, team, stage, openclaw_ready)
SEED = []


def _add(department, floor, desk, team, name, role, stage="active_advisory",
         openclaw_ready=False, capabilities=None):
    SEED.append({
        "display_name": name, "role": role,
        "floor_assignment": "floor_{:02d}".format(floor) if floor != 55 else "penthouse",
        "department": department,
        "desk_assignment": desk, "team": team, "stage": stage,
        "openclaw_ready": openclaw_ready,
        "capabilities": capabilities or [],
    })


# ── Trading telemetry workers (floors 41, 42, 43) ────────────────────
_add("OANDA Trading Floor",          41, "Account Wall",                 "trading_fx", "OANDA Account Monitor",      "Reads OANDA practice account summary (read-only).",
     stage="active_read_only", capabilities=["oanda_account_read"])
_add("OANDA Trading Floor",          41, "Account Wall",                 "trading_fx", "OANDA Position Watcher",     "Reports open positions from OANDA read-only API.",
     stage="active_read_only", capabilities=["oanda_positions_read"])
_add("OANDA Trading Floor",          41, "Account Wall",                 "trading_fx", "OANDA Trade History Clerk",  "Reads closed trade transactions (read-only).",
     stage="active_read_only", capabilities=["oanda_trades_read"])
_add("OANDA Trading Floor",          41, "Account Wall",                 "trading_fx", "OANDA PnL Reporter",         "Reports realized/unrealized P&L from account summary.",
     stage="active_advisory",  capabilities=["oanda_pnl_report"])
_add("OANDA Trading Floor",          41, "Live Market Stream",           "trading_fx", "FX Pricing Scout",            "Reads OANDA practice pricing.",
     stage="active_read_only", capabilities=["oanda_pricing_read"])
_add("OANDA Trading Floor",          41, "Live Market Stream",           "trading_fx", "FX Spread Watcher",           "Measures FX bid/ask spreads.",
     stage="active_read_only", capabilities=["spread_measurement"])

_add("Binance Trading Floor",        42, "Account Wall",                 "trading_crypto", "Binance Account Monitor",   "Reads Binance read-only account.",
     stage="active_read_only", capabilities=["binance_account_read"])
_add("Binance Trading Floor",        42, "Live Market Stream",           "trading_crypto", "Binance Market Data Scout", "Reads Binance testnet public market data.",
     stage="active_read_only", capabilities=["binance_public_read"])
_add("Binance Trading Floor",        42, "Live Market Stream",           "trading_crypto", "Crypto Spread Watcher",      "Crypto bid/ask spread observer.",
     stage="active_read_only", capabilities=["spread_measurement"])
_add("Binance Trading Floor",        42, "Account Wall",                 "trading_crypto", "Crypto Position Watcher",    "Reports balances/positions if read-only configured.",
     stage="active_advisory",  capabilities=["binance_positions_read"])

_add("Stock Exchange Trading Floor", 43, "Live Market Stream",           "trading_equities", "Stock Market Data Scout",  "Reads US equities quotes/bars.",
     stage="active_read_only", capabilities=["stocks_quote_read"])
_add("Stock Exchange Trading Floor", 43, "Live Market Stream",           "trading_equities", "Equity Quote Watcher",     "Live quote table watcher.",
     stage="active_read_only", capabilities=["stocks_quote_read"])
_add("Stock Exchange Trading Floor", 43, "Account Wall",                 "trading_equities", "Equity Position Watcher",  "Reports broker positions only if read-only endpoint exists.",
     stage="active_advisory",  capabilities=["stocks_positions_read"])
_add("Stock Exchange Trading Floor", 43, "Cross-Market Bus",             "trading_equities", "Cross-Market Correlation Clerk", "Correlates OANDA/Binance/Stocks bus.",
     stage="active_advisory",  capabilities=["correlation_pairing"])
_add("Stock Exchange Trading Floor", 43, "Audit Dispatch",               "trading_equities", "Trading Telemetry Auditor", "Audits trading telemetry payloads for label correctness.",
     stage="active_advisory",  capabilities=["audit_telemetry_labels"])

# ── Research Facility (floor 3) ───────────────────────────────────────
_add("Research Department", 3, "Research Intake Desk", "research_facility", "Research Intake Clerk",       "Triages research tasks.",            stage="active_advisory",  capabilities=["task_triage"])
_add("Research Department", 3, "Gatekeeper Desk",      "research_facility", "Web Research Gatekeeper",     "Web access gate — autonomous web access LOCKED.", stage="active_read_only", capabilities=["gatekeeper"])
_add("Research Department", 3, "Source Quality Desk",  "research_facility", "Source Quality Analyst",      "Evaluates source quality before archive.", stage="active_advisory",  capabilities=["source_quality"])
_add("Research Department", 3, "Literature Desk",      "research_facility", "Literature Scout",            "Tracks literature pointers.",         stage="active_advisory",  capabilities=["literature_tracking"])
_add("Research Department", 3, "Architecture Desk",    "research_facility", "Architecture Researcher",     "Catalogs architecture decisions.",    stage="active_advisory",  capabilities=["architecture_catalog"])
_add("Research Department", 3, "Code Pattern Desk",    "research_facility", "Code Pattern Researcher",     "Catalogs code patterns.",             stage="active_advisory",  capabilities=["code_pattern_catalog"])
_add("Research Department", 3, "Model Capability Desk","research_facility", "Model Capability Researcher", "Catalogs local model capabilities.",  stage="active_advisory",  capabilities=["model_capability"])
_add("Research Department", 3, "AirLLM Liaison Desk",  "research_facility", "AirLLM Research Liaison",     "Liaises with AirLLM advisory chamber (no AutoLoop).", stage="active_advisory", capabilities=["airllm_advisory_read"])
_add("Research Department", 3, "Report Writing Desk",  "research_facility", "Research Report Writer",      "Writes research reports to local archive.", stage="active_advisory", capabilities=["report_write"])
_add("Research Department", 3, "Research Archive",     "research_facility", "Experiment Archivist",        "Archives completed research.",        stage="active_advisory",  capabilities=["archive"])

# ── Maintenance (floor 33 — Diagnostics Department) ──────────────────
_add("Diagnostics Department", 33, "Service Health Desk",        "maintenance", "Service Health Mechanic",      "Inspects dashboard/sidecar liveness (no auto-repair).", stage="active_read_only", capabilities=["health_inspect"])
_add("Diagnostics Department", 33, "Port Monitor Wall",          "maintenance", "Port Watch Engineer",          "Watches 8765/8766/known sidecar ports.",                stage="active_read_only", capabilities=["port_watch"])
_add("Diagnostics Department", 33, "Disk Mount Monitor",         "maintenance", "Disk Space Steward",           "Tracks root + /vaults free space.",                     stage="active_read_only", capabilities=["disk_watch"])
_add("Diagnostics Department", 33, "Disk Mount Monitor",         "maintenance", "Mount Guardian",               "Verifies critical mounts present.",                     stage="active_read_only", capabilities=["mount_watch"])
_add("Diagnostics Department", 33, "Log Rotation Desk",          "maintenance", "Log Rotation Clerk",           "Reports log directory sizes (no auto-delete).",          stage="active_read_only", capabilities=["log_size_watch"])
_add("Diagnostics Department", 33, "Sidecar Watch Station",      "maintenance", "Sidecar Repair Technician",    "Diagnoses sidecar liveness; cannot kill/restart.",       stage="active_advisory",  capabilities=["sidecar_diagnose"])
_add("Diagnostics Department", 33, "Dashboard Asset Check Desk", "maintenance", "Dashboard Asset Inspector",    "Verifies static assets respond 200.",                    stage="active_read_only", capabilities=["asset_check"])
_add("Diagnostics Department", 33, "Worker Heartbeat Desk",      "maintenance", "Worker Heartbeat Mechanic",    "Verifies worker heartbeat freshness.",                  stage="active_advisory",  capabilities=["heartbeat_check"])
_add("Diagnostics Department", 33, "GPU Watch Station",          "maintenance", "GPU CUDA Monitor",             "Reads CUDA + GPU readiness from AirLLM chamber registry.", stage="active_read_only", capabilities=["gpu_read"])
_add("Diagnostics Department", 33, "AirLLM Storage Desk",        "maintenance", "AirLLM Storage Watcher",       "Reads /vaults/ai free space.",                          stage="active_read_only", capabilities=["airllm_disk_read"])

# ── Security (floor 28 — Security Department) ────────────────────────
_add("Security Department", 28, "Access Control Desk",         "security", "Access Control Guard",          "Verifies dashboard route allow-list.",         stage="active_advisory", capabilities=["access_control"])
_add("Security Department", 28, "Lock Matrix Wall",            "security", "Lock Matrix Sentinel",          "Watches all execution locks each tick.",       stage="active_advisory", capabilities=["lock_audit"])
_add("Security Department", 28, "OpenClaw Gate Guard",         "security", "OpenClaw Gatekeeper",           "Refuses OpenClaw execution unless reviewed.",  stage="active_advisory", capabilities=["openclaw_gate"])
_add("Security Department", 28, "Provider Access Guard Desk",  "security", "Provider Access Guard",         "Refuses external provider access.",            stage="active_advisory", capabilities=["provider_gate"])
_add("Security Department", 28, "Trading Execution Guard Desk","security", "Trading Execution Guard",       "Refuses trading execution unconditionally.",   stage="active_advisory", capabilities=["trade_gate"])
_add("Security Department", 28, "Payload Inspection Desk",     "security", "Payload Inspector",             "Inspects POST payloads for dangerous flags.",  stage="active_advisory", capabilities=["payload_inspect"])
_add("Security Department", 28, "Credential Redaction Desk",   "security", "Credential Redaction Guard",    "Scrubs API keys/secrets from any payload.",   stage="active_advisory", capabilities=["credential_redact"])
_add("Security Department", 28, "Incident Board",              "security", "Incident Clerk",                "Logs and tracks security incidents.",          stage="active_advisory", capabilities=["incident_log"])
_add("Security Department", 28, "Kernel Escort Station",       "security", "Kernel Escort",                 "Escorts kernel review packets to Penthouse.",  stage="active_advisory", capabilities=["kernel_escort"])

# ── IT / Networking (floor 35 — Infrastructure Services Department) ─
_add("Infrastructure Services Department", 35, "Network Operations Center", "it_networking", "Network Operations Manager", "Coordinates IT operations.",          stage="active_advisory", capabilities=["it_coord"])
_add("Infrastructure Services Department", 35, "Local Ports Map",           "it_networking", "Port Mapper",                "Maps all local listening ports.",     stage="active_read_only", capabilities=["port_map"])
_add("Infrastructure Services Department", 35, "API Gateway Desk",          "it_networking", "API Gateway Clerk",           "Documents /api/* routes available.",  stage="active_read_only", capabilities=["api_route_map"])
_add("Infrastructure Services Department", 35, "Sidecar Router Desk",       "it_networking", "Sidecar Router",              "Routes between sidecars.",            stage="active_advisory",  capabilities=["sidecar_route"])
_add("Infrastructure Services Department", 35, "Connectivity Scout Desk",   "it_networking", "Connectivity Scout",          "Probes OANDA/Binance/Stocks DNS reachability.", stage="active_read_only", capabilities=["dns_probe"])
_add("Infrastructure Services Department", 35, "Credential Vault Liaison",  "it_networking", "Credential Vault Liaison",    "Reports which env-credentials are loaded (names only).", stage="active_read_only", capabilities=["credential_status"])
_add("Infrastructure Services Department", 35, "Web Research Gatekeeper",   "it_networking", "Web Research Gatekeeper",     "Gates autonomous web access (LOCKED).", stage="active_advisory", capabilities=["web_gate"])
_add("Infrastructure Services Department", 35, "Media Route Desk",          "it_networking", "Media Route Technician",      "Routes media packets.",               stage="active_advisory",  capabilities=["media_route"])
_add("Infrastructure Services Department", 35, "Sound Route Desk",          "it_networking", "Sound Route Technician",      "Routes sound/speech packets.",        stage="active_advisory",  capabilities=["sound_route"])
_add("Infrastructure Services Department", 35, "Kernel Chat Route Desk",    "it_networking", "Kernel Chat Route Technician","Watches kernel chat sidecar :8766.",  stage="active_advisory",  capabilities=["chat_route"])

# ── Media / Speech / Audio ───────────────────────────────────────────
_add("Speech and Audio Department", 15, "Speech Route Desk",     "speech_media", "Speech Route Monitor",  "Monitors browser Web Speech availability.", stage="active_advisory", capabilities=["speech_route"])
_add("Speech and Audio Department", 15, "TTS Output Desk",       "speech_media", "TTS Output Clerk",      "Routes kernel replies to browser TTS.",     stage="active_advisory", capabilities=["tts_dispatch"])
_add("Speech and Audio Department", 15, "STT Intake Desk",       "speech_media", "STT Intake Clerk",      "Receives browser STT transcripts.",         stage="active_advisory", capabilities=["stt_intake"])
_add("Speech and Audio Department", 15, "Microphone Gate",       "speech_media", "Microphone Gatekeeper", "Honours browser mic permission.",            stage="candidate",        capabilities=["mic_gate"])
_add("Speech and Audio Department", 15, "Speaker Output Desk",   "speech_media", "Speaker Output Clerk",  "Manages TTS output volume.",                 stage="candidate",        capabilities=["speaker_gate"])
_add("Speech and Audio Department", 15, "Voice Queue Desk",      "speech_media", "Voice Queue Clerk",     "Queues outgoing TTS utterances.",            stage="active_advisory",  capabilities=["tts_queue"])
_add("Media Department",            14, "Media Routing Desk",    "speech_media", "Media Floor Liaison",   "Coordinates Floor 14 ↔ Floor 15.",          stage="active_advisory",  capabilities=["media_coord"])
_add("Speech and Audio Department", 15, "Kernel Speech Attendant","speech_media","Kernel Speech Attendant","Speaks kernel replies aloud (browser TTS).", stage="active_advisory", capabilities=["kernel_speech_route"])

# ── Penthouse staff (Colonel + Butler + 6 more) ──────────────────────
_add("Penthouse — QSB Kernel", 55, "Concierge Reception",   "penthouse_staff", "Colonel Concierge",          "Greets Ross; routes user to floors; summarizes reports.", stage="active_advisory", capabilities=["routing", "summarize_tower"])
_add("Penthouse — QSB Kernel", 55, "Butler Station",        "penthouse_staff", "Colonel Butler",             "Prepares Penthouse + tower daily briefing.",         stage="active_advisory", capabilities=["daily_briefing"])
_add("Penthouse — QSB Kernel", 55, "Floor Manager Office",  "penthouse_staff", "Penthouse Floor Manager",    "Floor manager of the Penthouse.",                    stage="active_advisory", capabilities=["floor_manage"])
_add("Penthouse — QSB Kernel", 55, "Kernel Liaison Office", "penthouse_staff", "Kernel Liaison Officer",     "Liaises between staff and QSB Kernel core.",         stage="active_advisory", capabilities=["kernel_liaison"])
_add("Penthouse — QSB Kernel", 55, "Speech Attendant",      "penthouse_staff", "Kernel Speech Attendant",    "Routes kernel replies to TTS.",                      stage="active_advisory", capabilities=["kernel_speech"])
_add("Penthouse — QSB Kernel", 55, "Memory Attendant",      "penthouse_staff", "Kernel Memory Attendant",    "Watches kernel memory routes.",                       stage="active_advisory", capabilities=["kernel_memory"])
_add("Penthouse — QSB Kernel", 55, "Report Clerk Desk",     "penthouse_staff", "Kernel Report Clerk",        "Collects manager reports for kernel review.",        stage="active_advisory", capabilities=["report_collect"])
_add("Penthouse — QSB Kernel", 55, "Security Escort",       "penthouse_staff", "Penthouse Security Escort",  "Escorts inbound packets through security checks.",   stage="active_advisory", capabilities=["escort"])

# ── Recruitment Agency (floor 38) ────────────────────────────────────
_add("Worker Recruitment Agency", 38, "Reception Desk",      "recruitment", "Reception Clerk",         "Greets candidates at reception.",       stage="active_advisory")
_add("Worker Recruitment Agency", 38, "Interview Room",      "recruitment", "Interview Panel",         "Conducts candidate interviews.",        stage="active_advisory")
_add("Worker Recruitment Agency", 38, "Training Room",       "recruitment", "Training Coach",          "Trains onboarded workers.",             stage="active_advisory")
_add("Worker Recruitment Agency", 38, "Capability Board",    "recruitment", "Capability Board Curator","Curates capability inventory.",          stage="active_advisory")
_add("Worker Recruitment Agency", 38, "Worker Registry Wall","recruitment", "Roster Wall Clerk",       "Maintains roster wall.",                stage="active_advisory")
_add("Worker Recruitment Agency", 38, "OpenClaw Readiness Gate", "recruitment", "OpenClaw Gatekeeper", "Reviews readiness — never enables exec.", stage="active_advisory", openclaw_ready=True)
_add("Worker Recruitment Agency", 38, "Dispatch Queue",      "recruitment", "Dispatch Queue Dispatcher","Manages dispatch queue.",               stage="active_advisory")
_add("Worker Recruitment Agency", 38, "Audit Desk",          "recruitment", "Recruitment Audit Clerk", "Audits recruitment events.",            stage="active_advisory")

# ── Risk (floor 30) + Audit (floor 31) extras ────────────────────────
_add("Permissions Department", 30, "Lock Matrix",       "risk", "Risk Sentinel",           "Audits all execution locks.",            stage="active_advisory")
_add("Permissions Department", 30, "Lock Matrix",       "risk", "Risk-On/Risk-Off Observer","Aggregates cross-market biases.",       stage="active_advisory")
_add("Audit Department",       31, "Ledger Counter",    "audit","Ledger Clerk",             "Appends to paper ledger.",              stage="active_advisory")
_add("Audit Department",       31, "Latest Entries",    "audit","Stock Ledger Clerk",       "Appends stock paper ledger entries.",   stage="active_advisory")
_add("Audit Department",       31, "Audit Pulse",       "audit","Audit Clerk",              "Pulses audit integrity check.",         stage="active_advisory")

# ── Strategy (floor 37) ──────────────────────────────────────────────
_add("Simulation Labs", 37, "Strategy Intelligence", "strategy", "Strategy Intelligence",   "Synthesizes paper strategy intel.", stage="active_advisory")
_add("Simulation Labs", 37, "Correlation Inputs",    "strategy", "Correlation Analyst",     "Correlation analysis.",             stage="active_advisory")
_add("Simulation Labs", 37, "Paper Signals",         "strategy", "Paper Strategy Analyst",  "Paper signal synthesis.",           stage="active_advisory")
_add("Simulation Labs", 37, "Cross-Market Inputs",   "strategy", "Equity Momentum Analyst", "Tracks equity momentum.",           stage="active_advisory")
_add("Simulation Labs", 37, "Cross-Market Inputs",   "strategy", "Cross-Market Correlation Clerk", "Cross-market correlation.",  stage="active_advisory")

# ── AirLLM advisory (floor 23) ───────────────────────────────────────
_add("AIR LLM Operations Department", 23, "Big Model Chamber", "airllm_advisory", "AirLLM Model Scout", "Reads AirLLM chamber registry (no execution).", stage="active_advisory")
_add("AIR LLM Operations Department", 23, "Advisory Desk",     "airllm_advisory", "Big Model Prompt Clerk", "Future manual Ask Big Air Model lane.", stage="candidate")
_add("AIR LLM Operations Department", 23, "Audit Desk",        "airllm_advisory", "Advisory Output Auditor","Audits advisory output.",               stage="active_advisory")


# ── V2 — Phase 2/3 extras (Accounts/Quantum/Lifts/Training/Data/Model Ops/Compliance/Emergency) ──
try:
    from .extra_workers import EXTRA as _EXTRA
    for _w in _EXTRA:
        SEED.append(_w)
except Exception:
    pass


# ── State helpers ──────────────────────────────────────────────────────
_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _normalize(w):
    w = dict(w)
    floor_n = _floor_num(w.get("floor_assignment"))
    zone_id, zone_name = zone_for_floor(floor_n or 38)
    w.setdefault("id", "w_" + uuid.uuid4().hex[:10])
    w.setdefault("worker_id", w["id"])
    w.setdefault("employment_status", "active")
    w.setdefault("recruitment_stage", w.get("stage", "active_advisory"))
    w.setdefault("health", "healthy")
    w.setdefault("heartbeat_ts", _now())
    w.setdefault("current_task", _task_for_stage(w.get("stage")))
    w.setdefault("last_packet", None)
    w.setdefault("last_report", None)
    w.setdefault("audit_count", 0)
    w.setdefault("openclaw_ready", bool(w.get("openclaw_ready")))
    w.setdefault("created_ts", _now())
    w.setdefault("updated_ts", _now())
    w.setdefault("zone_id", zone_id)
    w.setdefault("zone_name", zone_name)
    w.setdefault("floor_id", w.get("floor_assignment"))
    w.setdefault("floor_name", FLOOR_TO_DEPARTMENT.get(floor_n or 38, ("",))[0])
    w.setdefault("forbidden_actions", [
        "live_trading", "order_execution", "practice_order_execution",
        "openclaw_execution", "autonomous_dispatch",
        "direct_provider_access", "external_provider_execution",
        "live_dispatch", "trading_execution",
    ])
    w.setdefault("allowed_actions", _allowed_for_stage(w.get("stage")))
    # Universal locked fields — never editable by callers
    w["openclaw_execution_enabled"]   = False
    w["provider_access_enabled"]      = False
    w["autonomous_dispatch_enabled"]  = False
    w["trading_execution_enabled"]    = False
    return w


def _floor_num(s):
    if not s: return None
    if s == "penthouse": return 55
    import re
    m = re.match(r"^floor_(\d{1,2})$", s)
    return int(m.group(1)) if m else None


def _allowed_for_stage(stage):
    base = ["read_registries", "advisory_packet_emit", "audit_log_write"]
    if stage == "candidate":     return ["heartbeat_only"]
    if stage == "interviewed":   return ["heartbeat_only", "self_describe"]
    if stage == "onboarded":     return base + ["training_attend"]
    if stage == "probation":     return base + ["observation_only"]
    if stage == "active_read_only":  return base + ["observation_only"]
    if stage == "active_advisory":   return base + ["observation_only", "advisory_synthesis"]
    if stage == "ready_for_openclaw_review": return base + ["observation_only", "advisory_synthesis", "openclaw_review_packet"]
    return ["heartbeat_only"]


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
    }.get(stage or "active_advisory", "idle")


def _baseline_state():
    return {
        "registry": "qsb_tower_ops_worker_registry_v1",
        "phase": "QSB_TOWER_OPERATIONS_V1",
        "agency_name": "Worker Recruitment Agency",
        "agency_floor": "floor_38",
        "created_ts": _now(), "updated_ts": _now(),
        "workers": [_normalize(w) for w in SEED],
        "lifecycle_stages": list(VALID_STAGES),
        **LOCKED_FALSE,
    }


def _read_state():
    if not STATE_PATH.exists():
        _ensure_dirs()
        st = _baseline_state()
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        st = _baseline_state()
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st


def _write_state(state):
    state["updated_ts"] = _now()
    state.update(LOCKED_FALSE)
    state["execution_allowed"] = False
    state["paper_only"] = True
    state["advisory_only"] = True
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _stamp_heartbeats(state):
    now = _now()
    for w in state.get("workers", []):
        if w.get("recruitment_stage") == "rejected":
            w["health"] = "retired"; continue
        w["heartbeat_ts"] = now
        w["audit_count"] = (w.get("audit_count") or 0) + 1
    state["last_heartbeat_ts"] = now


def _append_log(record):
    _ensure_dirs()
    rec = dict(record); rec.setdefault("ts", _now())
    rec.setdefault("execution_allowed", False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


# ── Public API ─────────────────────────────────────────────────────────
def status():
    with _LOCK:
        state = _read_state()
        _stamp_heartbeats(state)
        _write_state(state)
        workers = state.get("workers") or []
        by_stage = {}
        for w in workers:
            by_stage[w.get("recruitment_stage", "active_advisory")] = by_stage.get(w.get("recruitment_stage", "active_advisory"), 0) + 1
        openclaw_ready = [w["id"] for w in workers if w.get("openclaw_ready") and w.get("recruitment_stage") != "rejected"]
        out = stamp_safe({
            "ok": True,
            "ts": _now(),
            "phase": state.get("phase"),
            "agency_name": state.get("agency_name"),
            "agency_floor": state.get("agency_floor"),
            "agency_status": "live",
            "total_workers": len(workers),
            "active_advisory":              by_stage.get("active_advisory", 0),
            "active_read_only":             by_stage.get("active_read_only", 0),
            "ready_for_openclaw_review":    by_stage.get("ready_for_openclaw_review", 0),
            "candidates":                   by_stage.get("candidate", 0),
            "rejected":                     by_stage.get("rejected", 0),
            "by_stage": by_stage,
            "openclaw_ready_count": len(openclaw_ready),
            "openclaw_ready_ids":   openclaw_ready,
            "last_heartbeat_ts": state.get("last_heartbeat_ts"),
        })
        return out


def workers():
    with _LOCK:
        state = _read_state()
        _stamp_heartbeats(state)
        _write_state(state)
        return stamp_safe({
            "ok": True,
            "ts": _now(),
            "phase": state.get("phase"),
            "agency_name": state.get("agency_name"),
            "agency_floor": state.get("agency_floor"),
            "workers": state.get("workers") or [],
            "lifecycle_stages": list(VALID_STAGES),
        })


def workers_by_floor(floor_id):
    """Return workers homed at a specific floor id, e.g. 'floor_41' or 'penthouse'."""
    st = workers()
    return [w for w in st["workers"] if w.get("floor_assignment") == floor_id]


def recruit(payload):
    payload = payload or {}
    name = (payload.get("display_name") or "").strip()
    if not name: return {"ok": False, "error": "display_name_required"}
    new = _normalize({
        "display_name": name,
        "role": payload.get("role") or "Recruited worker.",
        "floor_assignment": payload.get("floor_assignment") or "floor_38",
        "desk_assignment": payload.get("desk_assignment") or "Reception Desk",
        "team": payload.get("team") or "general",
        "stage": "candidate",
        "openclaw_ready": False,
        "capabilities": payload.get("capabilities") or [],
        "notes": payload.get("notes") or "",
    })
    with _LOCK:
        state = _read_state()
        state["workers"].append(new); _stamp_heartbeats(state); _write_state(state)
        _append_log({"event": "recruit", "worker_id": new["id"], "display_name": name})
    return stamp_safe({"ok": True, "worker": new})


def assign(payload):
    payload = payload or {}
    wid = payload.get("worker_id"); stage = payload.get("stage")
    if stage and stage not in VALID_STAGES:
        return {"ok": False, "error": "invalid_stage", "valid_stages": list(VALID_STAGES)}
    with _LOCK:
        state = _read_state()
        for w in state["workers"]:
            if w.get("id") == wid:
                if payload.get("floor_assignment"): w["floor_assignment"] = payload["floor_assignment"]
                if payload.get("desk_assignment"):  w["desk_assignment"] = payload["desk_assignment"]
                if stage:
                    w["stage"] = stage
                    w["recruitment_stage"] = stage
                    w["allowed_actions"] = _allowed_for_stage(stage)
                    w["current_task"] = _task_for_stage(stage)
                w["openclaw_execution_enabled"]   = False
                w["provider_access_enabled"]      = False
                w["autonomous_dispatch_enabled"]  = False
                w["trading_execution_enabled"]    = False
                _stamp_heartbeats(state); _write_state(state)
                _append_log({"event": "assign", "worker_id": wid, "stage": stage})
                return stamp_safe({"ok": True, "worker": w})
        return {"ok": False, "error": "worker_not_found", "worker_id": wid}


def retire(payload):
    payload = payload or {}; wid = payload.get("worker_id")
    with _LOCK:
        state = _read_state()
        for w in state["workers"]:
            if w.get("id") == wid:
                w["recruitment_stage"] = "rejected"
                w["stage"] = "rejected"
                w["health"] = "retired"
                w["current_task"] = "retired"
                w["allowed_actions"] = []
                w["openclaw_ready"] = False
                _stamp_heartbeats(state); _write_state(state)
                _append_log({"event": "retire", "worker_id": wid})
                return stamp_safe({"ok": True, "worker": w})
        return {"ok": False, "error": "worker_not_found", "worker_id": wid}


def openclaw_review(payload):
    payload = payload or {}; wid = payload.get("worker_id")
    with _LOCK:
        state = _read_state()
        for w in state["workers"]:
            if w.get("id") == wid:
                w["openclaw_ready"] = True
                w["recruitment_stage"] = "ready_for_openclaw_review"
                w["stage"] = "ready_for_openclaw_review"
                w["allowed_actions"] = _allowed_for_stage("ready_for_openclaw_review")
                w["current_task"] = "awaiting_openclaw_review"
                # NEVER toggle execution
                w["openclaw_execution_enabled"]   = False
                w["provider_access_enabled"]      = False
                w["autonomous_dispatch_enabled"]  = False
                w["trading_execution_enabled"]    = False
                _stamp_heartbeats(state); _write_state(state)
                _append_log({"event": "openclaw_review", "worker_id": wid,
                             "openclaw_ready": True, "openclaw_execution_enabled": False})
                return stamp_safe({"ok": True, "worker": w,
                                   "openclaw_ready": True,
                                   "openclaw_execution_enabled": False})
        return {"ok": False, "error": "worker_not_found", "worker_id": wid}
