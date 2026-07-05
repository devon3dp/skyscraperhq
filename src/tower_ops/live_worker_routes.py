"""Live worker routes — replaces the orbit-band model.

Each worker is given a *purposeful* route based on their team. The route
state advances deterministically with wall-clock time so the dashboard
shows workers actually walking between desks/lifts rather than orbiting
a single floor band.

This is pure metadata generation. No execution is unlocked.
"""

from datetime import datetime, timezone
from .safety_contract import stamp_safe
from .floor_room_positions import rooms_for


def _now(): return datetime.now(timezone.utc).isoformat()


# Per-team route templates: ordered list of (floor_id, room, route_reason).
ROUTE_TEMPLATES = {
    "trading_fx": [
        ("floor_41", "Pricing Desk",                  "reading practice pricing"),
        ("floor_41", "Lift Lobby",                    "walking to lift"),
        ("floor_30", "Lock Matrix",                   "reporting to risk"),
        ("floor_31", "Ledger Counter",                "writing ledger entry"),
        ("floor_44", "OANDA Desk",                    "reporting to accounts"),
        ("floor_41", "Manual Confirm Desk",           "waiting for manual confirm"),
        ("floor_41", "Practice Execution Desk",       "placing practice order"),
    ],
    "trading_crypto": [
        ("floor_42", "Testnet Market Feed",           "reading public market data"),
        ("floor_42", "Crypto Spread Watch",           "watching spread"),
        ("floor_42", "Account Wall",                  "reading testnet account"),
        ("floor_30", "Lock Matrix",                   "reporting to risk"),
        ("floor_31", "Ledger Counter",                "ledger update"),
        ("floor_44", "Binance Desk",                  "reporting to accounts"),
    ],
    "trading_equities": [
        ("floor_43", "Market Data Desk",              "reading stock quotes"),
        ("floor_43", "Equity Strategy Desk",          "writing paper signal"),
        ("floor_43", "Risk Checkpoint",               "risk check"),
        ("floor_44", "Stocks Desk",                   "reporting to accounts"),
        ("floor_31", "Ledger Counter",                "ledger update"),
    ],
    "openclaw_advisory": [
        ("floor_41", "OpenClaw Practice Proposal Desk","creating practice proposal"),
        ("floor_38", "OpenClaw Review Gate",          "readiness review"),
        ("floor_30", "Lock Matrix",                   "risk review"),
        ("floor_41", "Manual Confirm Desk",           "waiting for manual confirm"),
    ],
    "accounts": [
        ("floor_44", "Ledger Desk",                   "summarizing tower ledger"),
        ("floor_41", "Account Wall",                  "reading OANDA practice account"),
        ("floor_42", "Account Wall",                  "reading Binance account"),
        ("floor_43", "Account Wall",                  "reading Stocks account"),
        ("floor_31", "Audit Pulse",                   "cross-checking audit"),
    ],
    "security": [
        ("floor_28", "Lock Matrix Wall",              "auditing locks"),
        ("floor_30", "Lock Matrix",                   "reporting to risk"),
        ("floor_38", "OpenClaw Review Gate",          "OpenClaw gate check"),
        ("floor_28", "Incident Board",                "logging incidents"),
    ],
    "maintenance": [
        ("floor_33", "Service Health Desk",           "health check"),
        ("floor_33", "Port Monitor Wall",             "port scan"),
        ("floor_33", "Disk Mount Monitor",            "disk check"),
        ("floor_33", "Worker Heartbeat Desk",         "heartbeat audit"),
    ],
    "it_networking": [
        ("floor_35", "Network Operations Center",     "IT ops coordination"),
        ("floor_35", "Local Ports Map",               "port map update"),
        ("floor_35", "Sidecar Router Desk",           "sidecar routing"),
        ("floor_35", "API Gateway Desk",              "route documentation"),
    ],
    "research_facility": [
        ("floor_03", "Research Intake Desk",          "task triage"),
        ("floor_03", "Source Quality Desk",           "source review"),
        ("floor_03", "Report Writing Desk",           "writing report"),
        ("floor_03", "Architecture Desk",             "architecture catalog"),
    ],
    "training": [
        ("floor_08", "Reception",                     "candidate intake"),
        ("floor_08", "Safety and Locks Classroom",    "teaching safety"),
        ("floor_08", "Trading Telemetry Classroom",   "teaching telemetry"),
        ("floor_08", "Certification Board",           "certifying worker"),
    ],
    "penthouse_staff": [
        ("penthouse", "Concierge Reception",          "greeting Ross"),
        ("penthouse", "Kernel Core",                  "kernel liaison"),
        ("penthouse", "Speech Attendant",             "speech routing"),
        ("penthouse", "Colonel Observation Wall",     "observation"),
        ("penthouse", "Report Clerk Desk",            "manager reports"),
    ],
    "airllm_advisory": [
        ("floor_23", "Big Model Chamber",             "advisory read"),
        ("floor_23", "Advisory Desk",                 "queue review"),
        ("floor_31", "Audit Pulse",                   "advisory audit"),
    ],
    "quantum": [
        ("floor_45", "Reactor Room",                  "runtime detection"),
        ("floor_45", "Entropy Monitor",               "entropy read"),
        ("floor_45", "Symbolic Desk",                 "symbolic analysis"),
    ],
    "recruitment": [
        ("floor_38", "Reception Desk",                "candidate intake"),
        ("floor_38", "Interview Rooms",               "interview"),
        ("floor_38", "Training Room",                 "training assignment"),
        ("floor_38", "OpenClaw Review Gate",          "readiness check"),
    ],
    "speech_media": [
        ("floor_15", "TTS Output Desk",               "routing TTS"),
        ("floor_15", "STT Intake Desk",               "STT intake"),
        ("floor_14", "Media Routing Desk",            "media routing"),
        ("penthouse", "Speech Attendant",             "kernel speech"),
    ],
    "logistics": [
        ("floor_22", "Lift Operations Office",        "lift coordination"),
        ("floor_22", "Routing Desk",                  "worker routing"),
        ("floor_22", "Lift-01 Console",               "lift-01 control"),
    ],
    "model_ops": [
        ("floor_24", "Floor Manager Office",          "lane coordination"),
        ("floor_24", "Ollama Desk",                   "Ollama lane health"),
        ("floor_24", "AirLLM Desk",                   "advisory lane monitor"),
        ("floor_24", "Router Desk",                   "router update"),
    ],
}


def _route_for_team(team):
    return ROUTE_TEMPLATES.get(team) or [(None, "Main Floor", "idle_at_desk")]


def _hop_for_worker(w, period_seconds=18):
    """Pick which hop along the worker's route is currently active.

    Each hop lasts `period_seconds`. The hop index advances deterministically
    based on wall-clock + a per-worker offset, so workers stagger naturally.
    """
    route = _route_for_team(w.get("team") or w.get("department_id") or "general")
    if not route: return None, None, None
    offset = abs(hash(w.get("id") or w.get("worker_id") or "")) % len(route)
    now = datetime.now(timezone.utc).timestamp()
    idx = (int(now / period_seconds) + offset) % len(route)
    progress = (now % period_seconds) / period_seconds
    return idx, route, progress


# ── Public API ──────────────────────────────────────────────────────
def live_routes():
    """Return current route + hop for every worker (no orbit bands)."""
    from .worker_registry import workers as worker_list
    ws = (worker_list().get("workers") or [])
    out = []
    for w in ws:
        idx, route, progress = _hop_for_worker(w)
        if route is None:
            out.append({"worker_id": w.get("id"), "status": "idle"})
            continue
        cur_floor, cur_room, reason = route[idx]
        next_floor, next_room, _ = route[(idx + 1) % len(route)]
        same_floor = (cur_floor == next_floor)
        out.append({
            "worker_id":    w.get("id"),
            "badge_id":     w.get("badge_id"),
            "display_name": w.get("display_name"),
            "current_floor":(cur_floor or w.get("floor_assignment")),
            "current_room": cur_room,
            "target_floor": next_floor,
            "target_room":  next_room,
            "route_reason": reason,
            "lift_id":      _assign_lift(cur_floor, next_floor) if not same_floor else None,
            "eta_seconds":  int((1 - progress) * 18),
            "progress_0_to_1": round(progress, 3),
            "status": ("walking_to_room" if same_floor else
                       ("walking_to_lift" if progress < 0.4 else
                        ("inside_lift" if progress < 0.8 else "walking_to_room"))),
        })
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_V1.5",
                        "worker_routes": out, "count": len(out)})


def _assign_lift(src_floor_id, dst_floor_id):
    """Choose a lift that serves both floors. Deterministic."""
    if not src_floor_id or not dst_floor_id: return None
    def _n(s):
        if s == "penthouse": return 55
        import re; m = re.match(r"^floor_(\d{1,2})$", s); return int(m.group(1)) if m else 0
    a, b = sorted([_n(src_floor_id), _n(dst_floor_id)])
    if b <= 15: return "LIFT-01"
    if b <= 30: return "LIFT-02"
    if b <= 45: return "LIFT-03"
    if 41 in (a, b) or 42 in (a, b) or 43 in (a, b): return "LIFT-05"
    if 55 in (a, b): return "LIFT-04"
    return "LIFT-09"


def movement_state():
    lr = live_routes()
    by_status = {}
    for r in lr.get("worker_routes") or []:
        by_status[r.get("status", "idle")] = by_status.get(r.get("status", "idle"), 0) + 1
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_V1.5",
                        "total_workers": lr.get("count"),
                        "by_status": by_status,
                        "execution_allowed": False})
