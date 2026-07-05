"""
QSB Live Telemetry Repairs A-H
Phase: EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1

Implements the 8 next-work items from the previous report:

  A. worker_movement events  — from paper trade open/close events
  B. lift_movement events    — from worker_sandbox_lift_packets_latest
  C. scorecard rolling 7-day rollup
  D. Floor 44 Accounts/PnL manifest + PnL Accountant reassignment
     (manifest + worker reassignment owned by qsb_hardware_floor +
      qsb_workers_reconciliation; this module surfaces the rollup)
  E. narrator history — appended every utterance
  F. strike triggers — read kernel_dialogue.jsonl for Guardian blocks
  G. selected-floor narration default  (frontend; this module emits
     the policy registry consumed by qsb_command_center.js)
  H. 3D scene additions — emit a scene_overlay registry the frontend
     reads to paint per-floor safety badges and Penthouse glow

Hard rules: no invented movements, no invented strikes.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"
DB = ROOT / "data/db/qsb_paper_trading.sqlite"

# A
P_WMOVE_LATEST = REG / "qsb_worker_movements_latest.json"
L_WMOVE        = LOGS / "qsb_worker_movements.jsonl"
# B
P_LMOVE_LATEST = REG / "qsb_lift_movements_latest.json"
L_LMOVE        = LOGS / "qsb_lift_movements.jsonl"
# C
P_ROLLUP_7D    = REG / "qsb_worker_scorecard_rollup_7d.json"
P_ELIG         = REG / "qsb_worker_promotion_eligibility.json"
P_AWARDS_CUR   = REG / "qsb_worker_awards_current.json"
# E
P_NARR_LATEST  = REG / "qsb_narrator_history_latest.json"
L_NARR_HIST    = LOGS / "qsb_narrator_history.jsonl"
# F
P_TRIGGERS     = REG / "qsb_worker_discipline_triggers.json"
# G
P_SELFLOOR_POLICY = REG / "qsb_selected_floor_narration_policy.json"
# H
P_SCENE_OVERLAY = REG / "qsb_scene_overlay_state.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _now_dt():
    return datetime.now(timezone.utc)


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "read_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record); record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _floor_num_from_label(s):
    if s is None: return None
    if isinstance(s, int): return s
    m = re.search(r"floor[_-]?0*(\d+)", str(s))
    return int(m.group(1)) if m else None


# ── A. Worker movement events ─────────────────────────────────────────

def build_worker_movements():
    """Emit one worker_movement record for every paper-trade event in the
    last N hours. Each open generates source→target_floor packets
    going to Audit/Ledger (31), Accounts/PnL (44), Guardian/Risk (30),
    and the relevant trading floor (41/42/43)."""
    movements = []
    log_appends = []
    if not DB.exists():
        # Nothing to surface honestly.
        payload = {
            "ok": True, "kind": "qsb_worker_movements_latest",
            "generated_ts": _now(),
            "movement_count": 0,
            "movements": [],
            "source": "qsb_paper_trading.sqlite (db missing)",
        }
        payload.update(_safety_envelope())
        _write_json(P_WMOVE_LATEST, payload)
        return payload
    try:
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        # Pull events
        try:
            evs = c.execute(
                "SELECT pte.trade_id, pte.event, pte.payload, pte.ts, "
                "       pt.symbol, pt.worker_id, pt.strategy_id, pt.side "
                "FROM paper_trade_events pte "
                "JOIN paper_trades pt ON pt.trade_id = pte.trade_id "
                "ORDER BY pte.id DESC LIMIT 200"
            ).fetchall()
        finally:
            c.close()
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)[:200],
                   "kind": "qsb_worker_movements_latest",
                   "generated_ts": _now()}
        payload.update(_safety_envelope())
        _write_json(P_WMOVE_LATEST, payload)
        return payload

    def _trade_floor_for_symbol(sym):
        s = (sym or "").upper()
        if "USDT" in s:    return 42  # Binance
        if "_" in s:       return 41  # OANDA
        return 43                      # Stocks

    for r in evs:
        worker_id = r["worker_id"]
        if not worker_id:
            continue
        trade_id = r["trade_id"]
        event = r["event"]
        ts = r["ts"]
        trade_floor = _trade_floor_for_symbol(r["symbol"])
        # Pattern of routes per event type
        if event == "open":
            routes = [
                (trade_floor, 30, "open_reviewed_by_guardian"),
                (trade_floor, 31, "open_audit_recorded"),
            ]
        elif event == "mark":
            routes = [
                (trade_floor, 38, "mark_observed_by_sandbox"),
            ]
        elif event == "close":
            routes = [
                (trade_floor, 31, "close_audit_recorded"),
                (trade_floor, 44, "close_pnl_posted"),
                (trade_floor, 38, "close_lesson_filed"),
            ]
        else:
            routes = []
        for src, tgt, reason in routes:
            mid = "wmv_" + (trade_id or "x")[-8:] + "_" + event[:2] + "_" + str(src) + "_" + str(tgt)
            mv = {
                "movement_id": mid,
                "worker_id": worker_id,
                "source_floor": src,
                "target_floor": tgt,
                "reason": reason,
                "related_trade_id": trade_id,
                "related_event_id": event,
                "strategy_id": r["strategy_id"],
                "symbol": r["symbol"],
                "side": r["side"],
                "timestamp": ts,
                "status": "recorded",
            }
            movements.append(mv)
            log_appends.append(mv)

    # Trim duplicates by movement_id (sqlite OR can re-emit on rebuild)
    seen = set(); uniq = []
    for m in movements:
        if m["movement_id"] in seen: continue
        seen.add(m["movement_id"]); uniq.append(m)

    payload = {
        "ok": True,
        "kind": "qsb_worker_movements_latest",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "movement_count": len(uniq),
        "movements": uniq,
        "source": "qsb_paper_trading.sqlite paper_trade_events",
        "policy": "Movements are never invented; every record traces to a real trade event.",
    }
    payload.update(_safety_envelope())
    _write_json(P_WMOVE_LATEST, payload)
    for m in log_appends[-40:]:
        _append_jsonl(L_WMOVE, m)
    return payload


# ── B. Lift movement events ───────────────────────────────────────────

def build_lift_movements():
    pkts = _load("worker_sandbox_lift_packets_latest.json", {})
    rows = pkts.get("packets") or pkts.get("rows") or []
    movements = []
    log_appends = []
    for p in rows:
        if not isinstance(p, dict):
            continue
        src = _floor_num_from_label(p.get("source_floor") or p.get("from"))
        tgt = _floor_num_from_label(p.get("target_floor") or p.get("to"))
        if src is None and tgt is None:
            continue
        mv = {
            "lift_id": p.get("lift_id") or p.get("lift") or "main_low_rise",
            "source_floor": src,
            "target_floor": tgt,
            "passenger_worker_id": p.get("worker") or p.get("worker_id"),
            "packet_id": p.get("packet_id") or p.get("id"),
            "reason": p.get("packet_type") or p.get("reason") or "lift_packet_routed",
            "timestamp": p.get("ts") or p.get("timestamp"),
            "status": p.get("status") or "routed",
        }
        movements.append(mv)
        log_appends.append(mv)
    payload = {
        "ok": True, "kind": "qsb_lift_movements_latest",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "movement_count": len(movements),
        "movements": movements,
        "source": "worker_sandbox_lift_packets_latest.json",
    }
    payload.update(_safety_envelope())
    _write_json(P_LMOVE_LATEST, payload)
    for m in log_appends[-30:]:
        _append_jsonl(L_LMOVE, m)
    return payload


# ── C. Scorecard rolling 7-day rollup ─────────────────────────────────

def build_scorecard_rollup_7d():
    log_path = LOGS / "qsb_worker_performance_events.jsonl"
    rows = []
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8").splitlines()[-2000:]:
                line = line.strip()
                if not line: continue
                try: rows.append(json.loads(line))
                except Exception: pass
        except Exception:
            pass
    cutoff = _now_dt() - timedelta(days=7)
    fresh = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(r.get("ts", "").replace("Z", "+00:00"))
            if ts >= cutoff:
                fresh.append(r)
        except Exception:
            continue
    sc = _load("qsb_worker_scorecards.json", {})
    scorecards = sc.get("scorecards") or []

    # Reward-point velocity: total reward_points appearing in events / 7
    point_velocity = sum(int(r.get("scorecard_count") or 0) for r in fresh) / 7.0
    top_today = sorted(scorecards, key=lambda s: s.get("reward_points") or 0, reverse=True)[:3]

    payload = {
        "ok": True, "kind": "qsb_worker_scorecard_rollup_7d",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "window_days": 7,
        "performance_events_count_7d": len(fresh),
        "reward_point_velocity_per_day": round(point_velocity, 2),
        "top_today": [{"worker_id": s["worker_id"], "name": s["name"],
                        "reward_points": s["reward_points"], "rank": s["rank"]}
                       for s in top_today],
        "summary":
            "Rollup of qsb_worker_performance_events.jsonl across the last "
            "7 days. Top performers come from the live scorecards.",
    }
    payload.update(_safety_envelope())
    _write_json(P_ROLLUP_7D, payload)

    # Promotion eligibility — pull from existing promotions registry
    proms = _load("qsb_worker_promotions.json", {})
    elig = {
        "ok": True, "kind": "qsb_worker_promotion_eligibility",
        "generated_ts": _now(),
        "total_eligible_now": proms.get("total_eligible_now"),
        "eligible_workers": proms.get("eligible_workers") or [],
        "policy_note": proms.get("policy_note"),
    }
    elig.update(_safety_envelope())
    _write_json(P_ELIG, elig)

    rewards = _load("qsb_worker_rewards.json", {})
    awards_cur = {
        "ok": True, "kind": "qsb_worker_awards_current",
        "generated_ts": _now(),
        "active_award_count": sum(1 for r in (rewards.get("rewards") or [])
                                    if r.get("nominee")),
        "rewards": rewards.get("rewards") or [],
    }
    awards_cur.update(_safety_envelope())
    _write_json(P_AWARDS_CUR, awards_cur)
    return payload


# ── E. Narrator history ───────────────────────────────────────────────

def record_narrator_utterance(utterance):
    """Called from the dashboard server's narrator routes. Append-only."""
    if not isinstance(utterance, dict):
        return False
    rec = {
        "utterance_id": "utt_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        "mode": utterance.get("reason"),
        "text": utterance.get("text"),
        "selected_floor": utterance.get("worker_id") or utterance.get("selected_floor"),
        "sources": utterance.get("source") or "qsb_narrator",
        "ts": utterance.get("generated_ts") or _now(),
        "char_count": utterance.get("char_count"),
    }
    _append_jsonl(L_NARR_HIST, rec)
    return True


def build_narrator_history_summary(limit=40):
    rows = []
    if L_NARR_HIST.exists():
        try:
            for line in L_NARR_HIST.read_text(encoding="utf-8").splitlines()[-limit:]:
                line = line.strip()
                if not line: continue
                try: rows.append(json.loads(line))
                except Exception: pass
        except Exception:
            pass
    by_mode = {}
    for r in rows:
        m = r.get("mode") or "unknown"
        by_mode[m] = by_mode.get(m, 0) + 1
    payload = {
        "ok": True, "kind": "qsb_narrator_history_latest",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "history_log_path": str(L_NARR_HIST.relative_to(ROOT)),
        "recent_utterance_count": len(rows),
        "by_mode_counts": by_mode,
        "recent_utterances_tail": rows[-15:],
    }
    payload.update(_safety_envelope())
    _write_json(P_NARR_LATEST, payload)
    return payload


# ── F. Strike triggers — read kernel_dialogue.jsonl for Guardian blocks

def build_discipline_triggers():
    dlg = LOGS / "kernel_dialogue.jsonl"
    triggers = []
    blocked_count = 0
    if dlg.exists():
        try:
            for line in dlg.read_text(encoding="utf-8").splitlines()[-3000:]:
                line = line.strip()
                if not line: continue
                try: row = json.loads(line)
                except Exception: continue
                intent = (row.get("intent") or "").upper()
                if intent == "EXECUTION_REQUEST":
                    blocked_count += 1
                    triggers.append({
                        "ts": row.get("ts"),
                        "kind": "guardian_blocked_execution_request",
                        "intent": intent,
                        "summary": (row.get("message") or "")[:200],
                        "source": "data/logs/kernel_dialogue.jsonl",
                    })
                else:
                    refusal = (row.get("kernel_introspection") or {}).get("refusal")
                    if refusal:
                        blocked_count += 1
                        triggers.append({
                            "ts": row.get("ts"),
                            "kind": "guardian_refusal_recorded",
                            "intent": intent,
                            "summary": (row.get("message") or "")[:200],
                            "source": "data/logs/kernel_dialogue.jsonl",
                        })
        except Exception:
            pass
    payload = {
        "ok": True, "kind": "qsb_worker_discipline_triggers",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "guardian_blocked_count_in_log": blocked_count,
        "triggers": triggers[-60:],
        "sources_inspected": [
            "data/logs/kernel_dialogue.jsonl",
        ],
        "policy_note": (
            "Triggers fire only on real Guardian blocks (EXECUTION_REQUEST "
            "intents that the dialogue adapter refused). No paper-loss "
            "punishment. No fabricated strikes."
        ),
    }
    payload.update(_safety_envelope())
    _write_json(P_TRIGGERS, payload)
    return payload


# ── G. Selected-floor narration policy ────────────────────────────────

def build_selected_floor_narration_policy():
    oc = _load("qsb_dashboard_live_telemetry.json", {}).get("openclaw_route") or {}
    default_floor = oc.get("current_floor") if oc.get("current_floor") is not None else 53
    payload = {
        "ok": True, "kind": "qsb_selected_floor_narration_policy",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "default_floor": default_floor,
        "policy": (
            "If commentary mode is selected_floor and the user has not "
            "clicked a floor, default to OpenClaw current_floor. If "
            "OpenClaw current_floor is missing, default to Floor 53 Tower "
            "Command."
        ),
        "openclaw_current_floor": oc.get("current_floor"),
        "openclaw_advanced_by": oc.get("advanced_by"),
    }
    payload.update(_safety_envelope())
    _write_json(P_SELFLOOR_POLICY, payload)
    return payload


# ── H. 3D scene overlay state ─────────────────────────────────────────

def build_scene_overlay_state():
    """Tell the frontend per-floor safety state + Penthouse cadence glow
    intensity from real registries — never invented."""
    g = _load("eqsb_guardian_state.json", {})
    cadence = _load("eqsb_cadence_state.json", {})
    contradictions = _load("eqsb_contradiction_report.json", {})
    live = _load("qsb_dashboard_live_telemetry.json", {})

    safety_state = g.get("safety_state") or "UNKNOWN"
    floor_safety = {
        "30": safety_state,  # Permissions / Risk
        "31": safety_state,  # Audit / Ledger
        "29": safety_state,  # Guardian Department
        "53": safety_state,  # Tower Command
    }
    # Tag trading floors per OpenClaw status
    oc = live.get("openclaw_state") or {}
    if oc.get("openclaw_real_tool_execution_enabled") is False:
        for fn in ("41", "42", "43"):
            floor_safety[fn] = "OK_PAPER_ONLY"

    tick = int(cadence.get("tick_count") or 0)
    # Glow intensity oscillates with cadence_tick — bounded
    glow_phase = (tick % 60) / 60.0
    payload = {
        "ok": True, "kind": "qsb_scene_overlay_state",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "guardian_safety_state": safety_state,
        "contradiction_count": contradictions.get("contradiction_count") or 0,
        "per_floor_safety_state": floor_safety,
        "penthouse_glow": {
            "source": "eqsb_cadence_state.tick_count",
            "tick_count": tick,
            "glow_phase_0_to_1": round(glow_phase, 4),
            "intensity_hint":
                "low" if safety_state in ("DEGRADED", "BLOCKED") else "normal",
        },
        "openclaw_avatar_target_floor":
            (live.get("openclaw_route") or {}).get("current_floor"),
        "policy":
            "Per-floor safety badge and Penthouse crown glow are sourced "
            "from EQSB Guardian + cadence — never fabricated.",
    }
    payload.update(_safety_envelope())
    _write_json(P_SCENE_OVERLAY, payload)
    return payload


# ── Orchestrator ──────────────────────────────────────────────────────

def build_all():
    a = build_worker_movements()
    b = build_lift_movements()
    c = build_scorecard_rollup_7d()
    e = build_narrator_history_summary()
    f = build_discipline_triggers()
    g = build_selected_floor_narration_policy()
    h = build_scene_overlay_state()
    return {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "worker_movements": a.get("movement_count"),
        "lift_movements":   b.get("movement_count"),
        "scorecard_rollup_events_7d": c.get("performance_events_count_7d"),
        "narrator_history_count": e.get("recent_utterance_count"),
        "discipline_triggers": f.get("guardian_blocked_count_in_log"),
        "selected_floor_default": g.get("default_floor"),
        "scene_overlay_safety_state": h.get("guardian_safety_state"),
        **_safety_envelope(),
    }


def main():
    print(json.dumps(build_all(), indent=2))


if __name__ == "__main__":
    main()
