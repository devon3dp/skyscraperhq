#!/usr/bin/env python3
"""
QSB Tower V1 — Floor 45 Worker Recruitment Agency

Phase: QSB_TOWER_KERNEL_CHAT_AND_RECRUITMENT_AGENCY_V1

The Floor 45 Recruitment Agency creates, tracks, trains, and *visually*
dispatches sandbox-only worker candidates into QSB Tower workflows.

Hard contracts (enforced in code, not in config):
  * Every candidate is sandbox-only.
  * Every candidate stays `execution_allowed=false`,
    `worker_execution_enabled=false`, `advisory_or_paper_only=true`,
    `not_financial_advice=true` on every read and every write.
  * Tick advances onboarding/training stages and emits visual dispatch
    packets to the target floors. It does NOT enable real worker
    execution, autonomous dispatch, provider execution, OpenClaw real
    execution, or live trading. Ever.
  * No new ports. No new sidecars. The dashboard reads these registries
    through /api/unified and /api/floor_detail?floor=45.

Files maintained:
  data/registries/worker_recruitment_agency_status.json
  data/registries/worker_candidate_registry.json     (Floor 45 entries
                                                       appended; pre-existing
                                                       entries preserved)
  data/registries/worker_onboarding_queue.json       (Floor 45 entries
                                                       appended)
  data/registries/worker_training_assignments.json
  data/logs/worker_recruitment_agency.jsonl
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"
LOG  = ROOT / "data/logs/worker_recruitment_agency.jsonl"

STATUS_PATH    = REG / "worker_recruitment_agency_status.json"
CANDIDATE_PATH = REG / "worker_candidate_registry.json"
QUEUE_PATH     = REG / "worker_onboarding_queue.json"
TRAINING_PATH  = REG / "worker_training_assignments.json"

AGENCY_FLOOR_ID = "floor_45"
AGENCY_FLOOR_NUMBER = 45
AGENCY_NAME = "Worker Recruitment Agency"
PHASE = "QSB_TOWER_KERNEL_CHAT_AND_RECRUITMENT_AGENCY_V1"

# Universal locks — stamped on every write.
LOCKED_FALSE = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "stock_order_execution_enabled": False,
    "stock_live_trading_enabled": False,
    "stock_paper_order_execution_enabled": False,
    "binance_order_execution_enabled": False,
    "binance_live_trading_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False,
}

TRAINING_STAGES = (
    "intake",            # just walked in the door
    "screening",         # safety screening / sandbox-only validation
    "training_pod",      # rotating through training pods
    "assignment_board",  # waiting for desk assignment
    "dispatched",        # visually dispatched to target floor
)

# The 12 initial sandbox-only candidates the user asked for. Each entry
# includes a stable id, role, home floor, intended target floor, the
# skills they're being trained on, and the visual route they walk after
# dispatch. Locks remain false on every single one.
SEED_CANDIDATES = [
    {"worker_id": "f45_equity_market_scout",
     "display_name": "Equity Market Scout",
     "role": "Reads US equities quotes from Floor 43 gateway. Sandbox only.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_43",
     "skills": ["read_stock_floor", "quote_status", "advisory_only"],
     "team": "trading_equities"},
    {"worker_id": "f45_crypto_market_scout",
     "display_name": "Crypto Market Scout",
     "role": "Reads Binance testnet public market data. Sandbox only.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_42",
     "skills": ["read_binance_testnet", "public_market_data"],
     "team": "trading_crypto"},
    {"worker_id": "f45_fx_market_scout",
     "display_name": "FX Market Scout",
     "role": "Reads OANDA practice pricing. Sandbox only.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_41",
     "skills": ["read_oanda_practice", "quote_status"],
     "team": "trading_fx"},
    {"worker_id": "f45_cross_market_analyst",
     "display_name": "Cross-Market Analyst",
     "role": "Reads OANDA + Binance + Stocks; builds paper-only correlations.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_37",
     "skills": ["read_registries", "correlation_pairing", "advisory_only"],
     "team": "strategy"},
    {"worker_id": "f45_risk_gatekeeper",
     "display_name": "Risk Gatekeeper",
     "role": "Verifies execution locks remain closed before any packet.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_30",
     "skills": ["lock_audit", "risk_alerting"],
     "team": "risk"},
    {"worker_id": "f45_ledger_runner",
     "display_name": "Ledger Runner",
     "role": "Carries paper observations to the Floor 31 audit ledger.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_31",
     "skills": ["append_only_ledger", "paper_audit_trail"],
     "team": "audit"},
    {"worker_id": "f45_airllm_advisory_clerk",
     "display_name": "AirLLM Advisory Clerk",
     "role": "Reads AirLLM chamber registry. Never invokes the model.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_23",
     "skills": ["read_airllm_registry", "advisory_only"],
     "team": "airllm_advisory"},
    {"worker_id": "f45_kernel_liaison",
     "display_name": "Kernel Liaison",
     "role": "Carries kernel-review packets toward the Penthouse.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_53",
     "skills": ["kernel_review_packet", "advisory_only"],
     "team": "command"},
    {"worker_id": "f45_openclaw_sandbox_observer",
     "display_name": "OpenClaw Sandbox Observer",
     "role": "Observes the OpenClaw Visual Sandbox on Floor 38. Sees only.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_38",
     "skills": ["openclaw_sandbox_logging"],
     "team": "openclaw_advisory"},
    {"worker_id": "f45_strategy_backtester",
     "display_name": "Strategy Backtester",
     "role": "Runs sandbox backtests on Floor 37. Paper-only results.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_37",
     "skills": ["backtest_sandbox", "paper_signal_synthesis"],
     "team": "strategy"},
    {"worker_id": "f45_volatility_watcher",
     "display_name": "Volatility Watcher",
     "role": "Tracks paper-only volatility across markets.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_37",
     "skills": ["volatility_observation"],
     "team": "strategy"},
    {"worker_id": "f45_correlation_mapper",
     "display_name": "Correlation Mapper",
     "role": "Maps cross-market correlations to Floor 25 Agent Coordination.",
     "home_floor": AGENCY_FLOOR_ID, "target_floor": "floor_25",
     "skills": ["correlation_pairing", "agent_coordination_readiness"],
     "team": "strategy"},
]

_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs():
    REG.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_log(record):
    _ensure_dirs()
    record = dict(record)
    record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    record.setdefault("sandbox_only", True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _normalize_candidate(seed):
    """Project a seed entry into the full candidate schema. Locks are
    always stamped false. This runs on every read so we cannot drift."""
    c = dict(seed)
    c["sandbox_only"] = True
    c["execution_allowed"] = False
    c["advisory_or_paper_only"] = True
    c["not_financial_advice"] = True
    c["worker_execution_enabled"] = False
    c["provider_execution_enabled"] = False
    c["external_provider_execution_enabled"] = False
    c["openclaw_execution_enabled"] = False
    c["openclaw_real_tool_execution_enabled"] = False
    c["autonomous_dispatch_enabled"] = False
    c["live_dispatch_enabled"] = False
    c["direct_provider_access"] = False
    c.setdefault("home_floor", AGENCY_FLOOR_ID)
    c.setdefault("current_floor", AGENCY_FLOOR_ID)
    c.setdefault("target_floor", AGENCY_FLOOR_ID)
    c.setdefault("training_status", "intake")
    c.setdefault("assigned_routes", _routes_for(c.get("target_floor", AGENCY_FLOOR_ID)))
    c.setdefault("skills", [])
    c.setdefault("current_task",
                 _task_for_stage(c.get("training_status", "intake")))
    c.setdefault("last_seen_ts", _now())
    return c


def _routes_for(target_floor):
    """Visual route list — Floor 45 → target floor through audit/risk."""
    target_floor = str(target_floor or AGENCY_FLOOR_ID)
    base = [
        {"from": AGENCY_FLOOR_ID, "to": "floor_30",
         "route_type": "worker_recruitment_sandbox",
         "purpose": "risk_check_before_dispatch"},
        {"from": AGENCY_FLOOR_ID, "to": "floor_31",
         "route_type": "worker_recruitment_sandbox",
         "purpose": "audit_dispatch_event"},
        {"from": AGENCY_FLOOR_ID, "to": target_floor,
         "route_type": "worker_recruitment_sandbox",
         "purpose": "visual_dispatch"},
        {"from": AGENCY_FLOOR_ID, "to": "floor_53",
         "route_type": "worker_recruitment_sandbox",
         "purpose": "tower_command_summary"},
    ]
    # Floor 25 Agent Coordination + Floor 38 Sandbox always see new recruits.
    if target_floor != "floor_25":
        base.append({"from": AGENCY_FLOOR_ID, "to": "floor_25",
                     "route_type": "worker_recruitment_sandbox",
                     "purpose": "agent_coordination_visibility"})
    if target_floor != "floor_38":
        base.append({"from": AGENCY_FLOOR_ID, "to": "floor_38",
                     "route_type": "worker_recruitment_sandbox",
                     "purpose": "sandbox_visibility"})
    for r in base:
        r["sandbox_only"] = True
        r["execution_allowed"] = False
        r["worker_execution_enabled"] = False
    return base


def _task_for_stage(stage):
    return {
        "intake":           "intake_processing",
        "screening":        "safety_screening",
        "training_pod":     "in_training",
        "assignment_board": "awaiting_assignment",
        "dispatched":       "visual_dispatch_complete",
    }.get(stage, "idle")


def _next_stage(stage):
    order = list(TRAINING_STAGES)
    if stage not in order:
        return order[0]
    i = order.index(stage)
    if i >= len(order) - 1:
        return order[-1]
    return order[i + 1]


def _read_candidate_registry():
    raw = _read_json(CANDIDATE_PATH, [])
    if isinstance(raw, dict):
        # legacy / wrapped — normalize
        existing = raw.get("candidates") or []
    elif isinstance(raw, list):
        existing = raw
    else:
        existing = []
    return existing


def _write_candidate_registry(entries):
    _write_json(CANDIDATE_PATH, entries)


def _read_queue():
    raw = _read_json(QUEUE_PATH, [])
    if isinstance(raw, list):
        return raw
    return raw.get("queue") or []


def _write_queue(entries):
    _write_json(QUEUE_PATH, entries)


def _read_training():
    raw = _read_json(TRAINING_PATH, None)
    if not isinstance(raw, dict):
        return {
            "assignments": [],
            "stages": list(TRAINING_STAGES),
            "execution_allowed": False,
            "sandbox_only": True,
        }
    raw.setdefault("assignments", [])
    raw.setdefault("stages", list(TRAINING_STAGES))
    raw["execution_allowed"] = False
    raw["sandbox_only"] = True
    return raw


def _write_training(payload):
    payload["execution_allowed"] = False
    payload["sandbox_only"] = True
    payload["updated_ts"] = _now()
    _write_json(TRAINING_PATH, payload)


def _ensure_seed():
    """Idempotent: add the 12 Floor 45 seed candidates if any are missing.
    Pre-existing entries with different schemas are preserved untouched."""
    existing = _read_candidate_registry()
    by_id = {}
    for e in existing:
        if isinstance(e, dict):
            wid = e.get("worker_id") or e.get("candidate_id") or e.get("id")
            if wid:
                by_id[wid] = e

    added = []
    for seed in SEED_CANDIDATES:
        if seed["worker_id"] in by_id:
            continue
        added.append(_normalize_candidate(seed))

    if added:
        merged = list(existing) + added
        _write_candidate_registry(merged)
        for a in added:
            _append_log({"event": "recruit", "worker_id": a["worker_id"],
                         "display_name": a["display_name"],
                         "target_floor": a.get("target_floor")})

    # Queue: stage every Floor 45 worker through training if not already.
    queue = _read_queue()
    queue_ids = {(q.get("worker_id") or q.get("candidate_id"))
                 for q in queue if isinstance(q, dict)}
    new_queue = list(queue)
    for seed in SEED_CANDIDATES:
        if seed["worker_id"] in queue_ids:
            continue
        new_queue.append({
            "queue_id": "onboard_" + seed["worker_id"],
            "worker_id": seed["worker_id"],
            "candidate_id": seed["worker_id"],
            "display_name": seed["display_name"],
            "target_floor": seed.get("target_floor"),
            "training_status": "intake",
            "current_task": _task_for_stage("intake"),
            "execution_allowed": False,
            "sandbox_only": True,
            "advisory_or_paper_only": True,
            "not_financial_advice": True,
            "added_ts": _now(),
        })
    if len(new_queue) != len(queue):
        _write_queue(new_queue)

    # Training assignments: one row per Floor 45 worker, stage "intake".
    training = _read_training()
    assigns = training.get("assignments") or []
    assign_ids = {a.get("worker_id") for a in assigns if isinstance(a, dict)}
    for seed in SEED_CANDIDATES:
        if seed["worker_id"] in assign_ids:
            continue
        assigns.append({
            "worker_id": seed["worker_id"],
            "display_name": seed["display_name"],
            "target_floor": seed.get("target_floor"),
            "training_status": "intake",
            "current_task": _task_for_stage("intake"),
            "skills_learned": [],
            "skills_remaining": list(seed.get("skills") or []),
            "execution_allowed": False,
            "sandbox_only": True,
        })
    training["assignments"] = assigns
    _write_training(training)


def _floor45_candidates():
    """Return only the normalized Floor 45 candidates (filtered out of the
    shared registry so external/legacy entries don't bleed into the agency
    response)."""
    out = []
    raw = _read_candidate_registry()
    seed_ids = {s["worker_id"] for s in SEED_CANDIDATES}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        wid = (entry.get("worker_id") or entry.get("candidate_id")
               or entry.get("id"))
        if wid in seed_ids:
            out.append(_normalize_candidate(entry))
    return out


def _floor45_queue():
    queue = _read_queue()
    seed_ids = {s["worker_id"] for s in SEED_CANDIDATES}
    return [q for q in queue if isinstance(q, dict)
            and (q.get("worker_id") in seed_ids
                 or q.get("candidate_id") in seed_ids)]


def _agency_routes():
    """Outbound routes from Floor 45 → other tower floors. Sandbox only."""
    targets = [
        ("floor_25", "Agent Coordination"),
        ("floor_38", "Sandbox Operations"),
        ("floor_37", "Simulation / Strategy"),
        ("floor_30", "Permissions / Risk"),
        ("floor_31", "Audit / Ledger"),
        ("floor_53", "Tower Command"),
        ("penthouse", "Kernel Review"),
        ("floor_41", "OANDA Trading Floor"),
        ("floor_42", "Binance Trading Floor"),
        ("floor_43", "Stock Exchange Floor"),
        ("floor_23", "AirLLM Advisory"),
    ]
    return [{
        "from": AGENCY_FLOOR_ID, "to": fid, "name": name,
        "route_type": "worker_recruitment_sandbox",
        "sandbox_only": True,
        "execution_allowed": False,
        "worker_execution_enabled": False,
    } for fid, name in targets]


def _latest_events(limit=12):
    if not LOG.exists():
        return []
    try:
        lines = LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-int(limit):]
    except Exception:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": line})
    out.reverse()  # newest first
    return out


def _status_dict():
    candidates = _floor45_candidates()
    queue = _floor45_queue()
    training = _read_training()
    by_status = {}
    for c in candidates:
        by_status[c.get("training_status", "intake")] = by_status.get(
            c.get("training_status", "intake"), 0) + 1
    return {
        "ok": True,
        "ts": _now(),
        "phase": PHASE,
        "agency_name": AGENCY_NAME,
        "agency_floor": AGENCY_FLOOR_ID,
        "agency_floor_number": AGENCY_FLOOR_NUMBER,
        "candidate_count": len(candidates),
        "onboarding_queue_count": len(queue),
        "training_assignment_count": len(training.get("assignments") or []),
        "by_training_status": by_status,
        "stages": list(TRAINING_STAGES),
        "routes": _agency_routes(),
        "latest_events": _latest_events(8),
        "locks": dict(LOCKED_FALSE),
        "execution_allowed": False,
        "sandbox_only": True,
        "advisory_or_paper_only": True,
        "not_financial_advice": True,
    }


# ── Public API ─────────────────────────────────────────────────────────

def status():
    with _LOCK:
        _ensure_dirs()
        _ensure_seed()
        s = _status_dict()
        _write_json(STATUS_PATH, s)
        return s


def candidates():
    with _LOCK:
        _ensure_dirs()
        _ensure_seed()
        return {
            "ok": True,
            "ts": _now(),
            "phase": PHASE,
            "agency_name": AGENCY_NAME,
            "agency_floor": AGENCY_FLOOR_ID,
            "candidates": _floor45_candidates(),
            "locks": dict(LOCKED_FALSE),
            "execution_allowed": False,
            "sandbox_only": True,
        }


def onboarding_queue():
    with _LOCK:
        _ensure_dirs()
        _ensure_seed()
        return {
            "ok": True,
            "ts": _now(),
            "queue": _floor45_queue(),
            "execution_allowed": False,
            "sandbox_only": True,
        }


def training_assignments():
    with _LOCK:
        _ensure_dirs()
        _ensure_seed()
        t = _read_training()
        seed_ids = {s["worker_id"] for s in SEED_CANDIDATES}
        t["assignments"] = [a for a in (t.get("assignments") or [])
                            if a.get("worker_id") in seed_ids]
        t["execution_allowed"] = False
        t["sandbox_only"] = True
        return t


def tick():
    """Advance one onboarding/training step. Visual dispatch only — never
    enables real worker execution, autonomous dispatch, or provider
    execution. Returns the events produced this tick."""
    with _LOCK:
        _ensure_dirs()
        _ensure_seed()

        training = _read_training()
        assigns = training.get("assignments") or []
        registry = _read_candidate_registry()
        by_id = {}
        for e in registry:
            if isinstance(e, dict):
                wid = e.get("worker_id") or e.get("candidate_id") or e.get("id")
                if wid:
                    by_id[wid] = e

        events = []
        moved = 0
        for a in assigns:
            wid = a.get("worker_id")
            if wid not in by_id:
                continue
            cur = a.get("training_status") or "intake"
            nxt = _next_stage(cur)
            if nxt == cur:
                continue
            a["training_status"] = nxt
            a["current_task"] = _task_for_stage(nxt)
            # Reflect on the candidate registry as well so /api/floor_detail
            # picks the new stage up.
            by_id[wid]["training_status"] = nxt
            by_id[wid]["current_task"] = _task_for_stage(nxt)
            by_id[wid]["current_floor"] = (by_id[wid].get("target_floor")
                                            if nxt == "dispatched"
                                            else AGENCY_FLOOR_ID)
            by_id[wid]["last_seen_ts"] = _now()
            # Locks always re-stamped false on every write — no drift.
            by_id[wid]["execution_allowed"] = False
            by_id[wid]["worker_execution_enabled"] = False
            ev = {
                "event": "assign" if nxt == "dispatched" else "advance",
                "worker_id": wid,
                "display_name": a.get("display_name"),
                "from_stage": cur,
                "to_stage": nxt,
                "target_floor": a.get("target_floor"),
                "execution_allowed": False,
                "sandbox_only": True,
            }
            events.append(ev)
            _append_log(ev)
            moved += 1

        training["assignments"] = assigns
        _write_training(training)
        # Reserialize the merged registry (preserving any non-seed entries
        # untouched at the head).
        _write_candidate_registry(registry)

        _write_json(STATUS_PATH, _status_dict())

        return {
            "ok": True,
            "ts": _now(),
            "advanced": moved,
            "events": events,
            "execution_allowed": False,
            "sandbox_only": True,
            "locks": dict(LOCKED_FALSE),
        }


def floor_detail():
    """Build the rich Floor 45 detail block used by /api/floor_detail."""
    with _LOCK:
        _ensure_dirs()
        _ensure_seed()
        s = _status_dict()
        cands = _floor45_candidates()
        queue = _floor45_queue()
        training = _read_training()
        seed_ids = {x["worker_id"] for x in SEED_CANDIDATES}
        assignments = [a for a in (training.get("assignments") or [])
                       if a.get("worker_id") in seed_ids]
        return {
            "floor_number": AGENCY_FLOOR_NUMBER,
            "floor_id": AGENCY_FLOOR_ID,
            "display_name": AGENCY_NAME,
            "phase": PHASE,
            "recruitment_status": s,
            "candidates": cands,
            "onboarding_queue": queue,
            "training_assignments": assignments,
            "assigned_routes": _agency_routes(),
            "latest_recruitment_events": _latest_events(15),
            "safety_locks": dict(LOCKED_FALSE),
            "execution_allowed": False,
            "sandbox_only": True,
            "advisory_or_paper_only": True,
            "not_financial_advice": True,
        }


if __name__ == "__main__":
    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "tick":
        print(json.dumps(tick(), indent=2))
    elif cmd == "candidates":
        print(json.dumps(candidates(), indent=2))
    elif cmd == "queue":
        print(json.dumps(onboarding_queue(), indent=2))
    elif cmd == "training":
        print(json.dumps(training_assignments(), indent=2))
    elif cmd == "detail":
        print(json.dumps(floor_detail(), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown_command",
                          "command": cmd,
                          "valid": ["status", "tick", "candidates",
                                    "queue", "training", "detail"]},
                         indent=2))
        sys.exit(2)
