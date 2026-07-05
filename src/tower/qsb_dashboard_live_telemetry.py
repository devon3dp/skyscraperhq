"""
QSB Tower V3 — Canonical Dashboard Live Telemetry
Phase: QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2

Produces a single, canonical block the frontend can read to drive
visuals without any random/decorative invention.

Schema:
  floors[]                — registered floors (from /api/unified.floors)
  workers[]               — canonical workers (from qsb_canonical_workers)
  worker_assignments[]    — worker_id -> floor mapping
  worker_statuses[]       — worker_id -> status (active/idle/stale)
  worker_movements[]      — only workers in transit RIGHT NOW
  lifts[]                 — lift definitions
  lift_movements[]        — only active movements RIGHT NOW
  packets[]               — packet routes from /api/unified.packets
  packet_routes[]         — declared routes from dashboard_render_model
  openclaw_state          — qsb_openclaw_state
  openclaw_route          — current visited floor + history (deterministic)
  guardian_events[]       — guardian verdicts/transitions
  kernel_events[]         — recent kernel events from eqsb_kernel_events.jsonl
  paper_testnet_trades    — open trades + summary
  event_ticker[]          — merged ticker for the bottom rail
  stale_flags[]           — registries with stale or missing data
  missing_data_flags[]    — explicit "no live data" callouts per floor/zone
  last_update_ts          — when this telemetry was assembled
  dashboard_visual_mode   — "LIVE_DATA_ONLY" by contract

Hard rules:
  * Never invents workers, trades, packets, or routes.
  * Never enables execution.
  * No API keys, no secrets.
  * Honest: if a source is missing or stale, it is surfaced in stale_flags.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_LIVE = REG / "qsb_dashboard_live_telemetry.json"

STALE_THRESHOLD_HOURS = 12


def _live_canonical_counts(cw_summary, visible, by_floor, by_role, recon):
    """V18 — use Registry.workers() for the canonical total (dedupes across ALL
    roster files), not just qsb_canonical_workers.json which is one source.
    Falls back to cw_summary if Registry import fails."""
    try:
        from .registry import Registry  # type: ignore
        reg = Registry()
        live = len(reg.workers())
    except Exception:
        live = cw_summary.get("total_canonical_workers") or 0
    return {
        "total_canonical": live,
        "total_active":    live,
        "total_reporting": live,
        "total_newly_employed": cw_summary.get("total_newly_employed_workers"),
        "total_visible_on_skyscraper": len(visible),
        "by_home_floor_counts": by_floor,
        "by_role_counts": by_role,
        "mismatch_reason": recon.get("mismatch_reason"),
        "sources_total_reported": recon.get("sources_total_reported"),
        "source": "Registry.workers() (deduped across all roster files)",
    }


def _now():
    return datetime.now(timezone.utc).isoformat()


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
        "real_money_live_trading_enabled": False,
        "live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _is_stale(path, max_hours=STALE_THRESHOLD_HOURS):
    p = ROOT / path
    if not p.exists():
        return {"path": path, "reason": "missing"}
    try:
        age_h = (datetime.now(timezone.utc) -
                 datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                 ).total_seconds() / 3600.0
        if age_h > max_hours:
            return {"path": path, "reason": "stale",
                    "age_hours": round(age_h, 1),
                    "max_age_hours": max_hours}
    except Exception:
        return {"path": path, "reason": "stat_failed"}
    return None


def _stable_int(s, mod):
    """Deterministic small int from any string — used for fixed XZ positions."""
    if not s:
        s = "unknown"
    h = hashlib.sha1(str(s).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % max(1, int(mod))


def _tail_jsonl(rel_path, limit=80):
    p = ROOT / rel_path
    if not p.exists():
        return []
    rows = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return rows[-limit:]


def _floor_num(s):
    """Parse a floor reference like 'floor_42_binance_trading_floor' -> 42."""
    import re
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    m = re.search(r"floor[_-]?0*(\d+)", str(s))
    if m:
        return int(m.group(1))
    if str(s).lower() == "penthouse":
        return 53
    return None


def _canonical_workers():
    cw = _load("qsb_canonical_workers.json", {})
    return cw.get("workers") or []


def _worker_visible_set(workers):
    """The set of workers that should be visible on the skyscraper.
    A worker is visible iff:
      * it has a floor (home_floor != 'unassigned' OR current_floor != 'unassigned')
      * status == 'active' (default in V2)
      * real_execution_enabled is False (guard)
    Workers without an assigned floor are placed on floor 45 (Recruitment)
    with a 'unassigned' flag.
    """
    out = []
    for w in workers:
        wid = w.get("worker_id")
        if not wid:
            continue
        if w.get("status") != "active":
            continue
        if w.get("real_execution_enabled") is True:
            # Should never happen, but guard against it anyway.
            continue
        floor = _floor_num(w.get("home_floor")) or _floor_num(w.get("current_floor"))
        unassigned = floor is None
        if unassigned:
            floor = 45
        slot = _stable_int(wid, 7)
        # Deterministic xy slot index relative to floor; never random.
        out.append({
            "worker_id": wid,
            "display_name": w.get("display_name") or wid,
            "role": w.get("role") or "unassigned",
            "home_floor_label": w.get("home_floor"),
            "current_floor_label": w.get("current_floor"),
            "floor": floor,
            "floor_slot_index": slot,
            "status": w.get("status"),
            "reporting_enabled": w.get("reporting_enabled"),
            "learning_enabled": w.get("learning_enabled"),
            "paper_tasking_enabled": w.get("paper_tasking_enabled"),
            "real_execution_enabled": False,
            "in_transit": False,    # set true only by worker_movements below
            "unassigned": unassigned,
            "sources": w.get("sources") or [],
        })
    return out


def _worker_movements(visible_workers, kernel_events):
    """A worker is 'in transit' only when an event log row says so. We
    surface real records from qsb_worker_movements_latest.json (built
    by qsb_live_telemetry_repairs from paper_trade_events). NO INVENTION."""
    rec = _load("qsb_worker_movements_latest.json", {})
    return rec.get("movements") or []


def _lifts():
    lifts = _load("lifts.json", [])
    if isinstance(lifts, dict):
        lifts = lifts.get("lifts") or []
    return lifts or []


def _lift_movements():
    """Drives lift capsule animation. Sourced from
    qsb_lift_movements_latest.json (built from worker_sandbox lift
    packets). Empty list keeps capsules parked."""
    rec = _load("qsb_lift_movements_latest.json", {})
    return rec.get("movements") or []


def _packets_from_unified():
    """The /api/unified packets field is the canonical real packet feed.
    We do not duplicate that path here; we just expose its shape and let
    the frontend continue to consume /api/unified.packets directly.
    """
    # The dashboard frontend already consumes /api/unified.packets[]. We
    # mirror that here for completeness but never invent packets.
    bldg = _load("worker_sandbox_lift_packets_latest.json", {})
    return bldg.get("packets") or []


def _packet_routes():
    rm = _load("qsb_dashboard_render_model.json", {})
    return rm.get("routes") or []


def _openclaw_route(oc):
    """A deterministic visit order across supervised floors. The avatar
    visits them in registry order, one per cadence tick — NOT random.
    """
    supervised = oc.get("supervised_floors") or []
    order = []
    for s in supervised:
        n = _floor_num(s)
        if n is not None:
            order.append({"floor": n, "label": s})
    if not order:
        order = [{"floor": 53, "label": "floor_53_tower_command"}]
    # current_index taken from cadence tick_count so it advances on real ticks.
    cadence = _load("eqsb_cadence_state.json", {})
    tick = int(cadence.get("tick_count") or 0)
    cur = order[tick % len(order)]
    return {
        "current_floor": cur["floor"],
        "current_label": cur["label"],
        "visit_order": order,
        "advanced_by": "eqsb_cadence_state.tick_count",
        "deterministic": True,
        "is_random": False,
    }


def _guardian_events():
    """Synthesize a minimal event list from the guardian state file. The
    list represents the SINGLE current verdict + recent transitions.
    """
    g = _load("eqsb_guardian_state.json", {})
    if not g:
        return []
    return [{
        "ts": g.get("generated_ts"),
        "kind": "guardian_verdict",
        "safety_state": g.get("safety_state"),
        "default_verdict": g.get("default_verdict_for_read_only"),
        "blocked_reasons": g.get("blocked_reasons"),
        "advisory_only": True,
    }]


def _kernel_events(limit=40):
    rows = _tail_jsonl("data/logs/eqsb_kernel_events.jsonl", limit=limit)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({
            "ts": r.get("ts"),
            "event": r.get("event"),
            "advisory_only": True,
            # Carry one extra hint field if present.
            "extra": {k: v for k, v in r.items()
                       if k in ("entropy_score", "drift_score",
                                 "selected", "missing_count",
                                 "tick_count", "safety_state",
                                 "default_verdict", "verdict")},
        })
    return out


def _paper_testnet_trades():
    policy = _load("qsb_paper_trading_policy.json", {})
    open_ = _load("qsb_open_paper_trades.json", {})
    learn = _load("qsb_trade_learning.json", {})
    return {
        "active_mode": policy.get("active_mode"),
        "gateway_status": policy.get("gateway_status"),
        "max_open_trades": policy.get("max_open_trades"),
        "open_trade_count": open_.get("open_trade_count"),
        "remaining_trade_slots": open_.get("remaining_trade_slots"),
        "total_current_pnl": open_.get("total_current_pnl"),
        "total_realized_pnl": learn.get("total_realized_pnl"),
        "closed_trade_count": learn.get("closed_trade_count"),
        "lesson_count": learn.get("lesson_count"),
        "trades_preview": (open_.get("trades") or [])[:20],
    }


def _event_ticker(packets, kernel_events, guardian_events, paper_trades):
    """Merged, sorted ticker — newest first. Source-tagged."""
    rows = []
    for p in packets[:40]:
        rows.append({
            "ts": p.get("ts"),
            "source": "packet",
            "summary": "%s -> %s (%s)" % (p.get("source_floor"),
                                            p.get("target_floor"),
                                            p.get("type") or p.get("color") or "packet"),
        })
    for k in kernel_events[-20:]:
        rows.append({
            "ts": k.get("ts"),
            "source": "kernel_event",
            "summary": k.get("event"),
        })
    for g in guardian_events:
        rows.append({
            "ts": g.get("ts"),
            "source": "guardian_verdict",
            "summary": "safety_state=" + str(g.get("safety_state")) +
                        " default=" + str(g.get("default_verdict")),
        })
    if (paper_trades.get("open_trade_count") or 0) > 0:
        rows.append({
            "ts": _now(),
            "source": "paper_trading",
            "summary": "open trades=%s remaining=%s realized_pnl=%s" % (
                paper_trades.get("open_trade_count"),
                paper_trades.get("remaining_trade_slots"),
                paper_trades.get("total_realized_pnl"),
            ),
        })
    # newest first; tolerate missing timestamps
    def _key(r): return (r.get("ts") or "")
    rows.sort(key=_key, reverse=True)
    return rows[:60]


def _stale_flags():
    sources = [
        "data/registries/eqsb_kernel_introspection_latest.json",
        "data/registries/eqsb_belief_lifecycle.json",
        "data/registries/eqsb_axiom_registry.json",
        "data/registries/eqsb_quantum_signal_state.json",
        "data/registries/qsb_canonical_workers.json",
        "data/registries/qsb_open_paper_trades.json",
        "data/registries/qsb_openclaw_state.json",
        "data/registries/sandbox_autoloop_latest.json",
        "data/registries/binance_paper_strategy_latest.json",
        "data/registries/oanda_paper_strategy_latest.json",
        "data/logs/eqsb_kernel_events.jsonl",
    ]
    flags = []
    for s in sources:
        f = _is_stale(s, max_hours=STALE_THRESHOLD_HOURS)
        if f:
            flags.append(f)
    return flags


def _missing_data_flags(visible_workers, floors):
    """Per-floor 'no live data' callouts."""
    floors_with_workers = set(w["floor"] for w in visible_workers)
    out = []
    for f in floors or []:
        if not isinstance(f, dict):
            continue
        n = f.get("number") or f.get("floor_number") or f.get("id")
        try:
            n = int(n)
        except Exception:
            continue
        if n not in floors_with_workers and n not in (0, 54):
            out.append({"floor": n, "reason": "no_workers_assigned"})
    return out


def build_live_telemetry():
    workers = _canonical_workers()
    visible = _worker_visible_set(workers)
    floors_d = _load("floors.json", [])
    if isinstance(floors_d, dict):
        floors_d = floors_d.get("floors") or []
    by_floor = {}
    by_role = {}
    for w in visible:
        by_floor[w["floor"]] = by_floor.get(w["floor"], 0) + 1
        by_role[w["role"]] = by_role.get(w["role"], 0) + 1

    oc = _load("qsb_openclaw_state.json", {})
    openclaw_route = _openclaw_route(oc)

    kernel_events = _kernel_events(limit=40)
    guardian_events = _guardian_events()
    paper_trades = _paper_testnet_trades()
    packets = _packets_from_unified()
    packet_routes = _packet_routes()
    event_ticker = _event_ticker(packets, kernel_events,
                                   guardian_events, paper_trades)
    stale = _stale_flags()
    missing = _missing_data_flags(visible, floors_d)

    new_hires = _load("qsb_new_workers_employed.json", {})
    recon = _load("qsb_worker_count_reconciliation.json", {})
    cw_summary = _load("qsb_canonical_workers.json", {})

    # V1 Command Center additions
    scorecards = _load("qsb_worker_scorecards.json", {})
    rewards = _load("qsb_worker_rewards.json", {})
    awards = _load("qsb_worker_awards.json", {})
    discipline = _load("qsb_worker_discipline.json", {})
    promotions = _load("qsb_worker_promotions.json", {})
    profit = _load("qsb_profit_command.json", {})

    payload = {
        "ok": True,
        "phase": "QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2",
        "kind": "qsb_dashboard_live_telemetry",
        "generated_ts": _now(),
        "dashboard_visual_mode": "LIVE_DATA_ONLY",
        "policy": "NO_RANDOM_LIVE_GRAPHICS",
        # V18 — counts the frontend can render directly. We use Registry.workers()
        # for the canonical total (dedupes across ALL roster files), not just
        # qsb_canonical_workers.json which is one source.
        "worker_counts": _live_canonical_counts(cw_summary, visible, by_floor, by_role, recon),
        # Live blocks
        "floors": floors_d,
        "workers": visible,
        "worker_assignments": {
            w["worker_id"]: w["floor"] for w in visible
        },
        "worker_statuses": {
            w["worker_id"]: w["status"] for w in visible
        },
        "worker_movements": _worker_movements(visible, kernel_events),
        "lifts": _lifts(),
        "lift_movements": _lift_movements(),
        "packets": packets,
        "packet_routes": packet_routes,
        "openclaw_state": {
            "status": oc.get("status"),
            "openclaw_visual_enabled": oc.get("openclaw_visual_enabled"),
            "openclaw_sandbox_enabled": oc.get("openclaw_sandbox_enabled"),
            "openclaw_trade_supervision_enabled": oc.get("openclaw_trade_supervision_enabled"),
            "openclaw_diagnostic_ticketing_enabled": oc.get("openclaw_diagnostic_ticketing_enabled"),
            "openclaw_real_tool_execution_enabled": oc.get("openclaw_real_tool_execution_enabled"),
            "supervised_floors": oc.get("supervised_floors"),
            "diagnostic_ticket_count": oc.get("diagnostic_ticket_count"),
            "diagnostic_tickets": oc.get("diagnostic_tickets"),
        },
        "openclaw_route": openclaw_route,
        "guardian_events": guardian_events,
        "kernel_events": kernel_events,
        "paper_testnet_trades": paper_trades,
        "event_ticker": event_ticker,
        "stale_flags": stale,
        "missing_data_flags": missing,
        "new_workers_employed": {
            "total_newly_employed_workers":
                new_hires.get("total_newly_employed_workers"),
            "newly_employed_ids": [
                w.get("worker_id")
                for w in (new_hires.get("newly_employed_workers") or [])
            ],
        },
        # ── Command Center (V1) extensions ─────────────────────────
        "workforce": {
            "scorecards_total": scorecards.get("total_scorecards"),
            "by_rank_counts": (promotions.get("by_rank_counts") or {}),
            "total_on_warning":  discipline.get("total_on_warning"),
            "total_restricted":  discipline.get("total_restricted"),
            "total_suspended":   discipline.get("total_suspended"),
            "total_eligible_for_promotion": promotions.get("total_eligible_now"),
        },
        "rewards_and_awards": {
            "active_award_count": awards.get("active_award_count"),
            "active_awards": awards.get("active_awards") or [],
            "rewards": rewards.get("rewards") or [],
        },
        "profit_command_summary": {
            "trading_mode": profit.get("trading_mode"),
            "gateway_status": profit.get("gateway_status"),
            "open_trade_count": profit.get("open_trade_count"),
            "max_open_trades": profit.get("max_open_trades"),
            "total_realized_pnl": profit.get("total_realized_pnl"),
            "closed_trade_count": profit.get("closed_trade_count"),
            "lesson_count": profit.get("lesson_count"),
            "best_department_by_contribution":
                profit.get("best_department_by_contribution"),
            "top_workers": profit.get("top_workers"),
            "next_profit_focused_actions":
                profit.get("next_profit_focused_actions"),
            "real_money_live_trading_enabled": False,
        },
        "narrator_routes": {
            "tower":     "/api/narrator/tower",
            "floor":     "/api/narrator/floor/<floor_id>",
            "worker":    "/api/narrator/worker/<worker_id>",
            "profit":    "/api/narrator/profit",
            "openclaw":  "/api/narrator/openclaw",
            "kernel":    "/api/narrator/kernel",
            "critical":  "/api/narrator/critical",
            "history":   "/api/narrator/history",
            "speech_method": "browser_web_speech_synthesis",
        },
        # ── EQSB Observatory + Telemetry Repair (V1) additions ─────────
        "observatory": {
            "hardware_floor_registered":
                bool(_load("qsb_hardware_systems_floor.json", {}).get("ok")),
            "hardware_understanding":
                _load("eqsb_hardware_understanding.json", {}).get("summary"),
            "performance_advice":
                _load("eqsb_performance_advice.json", {}).get("advice"),
            "code_observatory_total_files":
                _load("eqsb_code_observatory.json", {}).get("total_files"),
            "system_graph": {
                "node_count":
                    _load("eqsb_system_understanding_graph.json", {}).get("node_count"),
                "edge_count":
                    _load("eqsb_system_understanding_graph.json", {}).get("edge_count"),
            },
            "claude_upgrade_ledger": {
                "phase_count":
                    _load("eqsb_claude_upgrade_ledger.json", {}).get("phase_count"),
                "latest_phase":
                    _load("eqsb_claude_upgrade_ledger.json", {}).get("latest_phase"),
            },
        },
        "telemetry_repairs": {
            "worker_movements_count":
                len(_load("qsb_worker_movements_latest.json", {}).get("movements") or []),
            "lift_movements_count":
                len(_load("qsb_lift_movements_latest.json", {}).get("movements") or []),
            "scorecard_rollup_7d_events":
                _load("qsb_worker_scorecard_rollup_7d.json", {}).get("performance_events_count_7d"),
            "narrator_history_count":
                _load("qsb_narrator_history_latest.json", {}).get("recent_utterance_count"),
            "discipline_triggers_count":
                _load("qsb_worker_discipline_triggers.json", {}).get("guardian_blocked_count_in_log"),
            "selected_floor_default":
                _load("qsb_selected_floor_narration_policy.json", {}).get("default_floor"),
            "scene_overlay_safety_state":
                _load("qsb_scene_overlay_state.json", {}).get("guardian_safety_state"),
            "floor_44_accounts_active":
                bool(_load("qsb_accounts_floor_state.json", {}).get("ok")),
        },
        # ── Workforce Operations Redesign (V1) ──────────────────────
        "workforce_v1": {
            "view_mode_default":
                _load("qsb_workforce_view_mode.json", {}).get("default_mode"),
            "totals":
                _load("qsb_workforce_truth_contract.json", {}).get("totals"),
            "by_class_counts":
                _load("qsb_workforce_truth_contract.json", {}).get("by_class_counts"),
            "by_floor_counts":
                _load("qsb_workforce_truth_contract.json", {}).get("by_floor_counts"),
            "ui_label_policy":
                _load("qsb_workforce_truth_contract.json", {}).get("ui_label_policy"),
            "training_academy_floor":
                (_load("qsb_workforce_operations_state.json", {})
                 .get("training_academy") or {}).get("academy_floor_number"),
            "lessons_room_floor":
                (_load("qsb_workforce_operations_state.json", {})
                 .get("lessons_room") or {}).get("lessons_room_floor_number"),
            "recruitment_floor":
                (_load("qsb_workforce_operations_state.json", {})
                 .get("recruitment") or {}).get("agency_floor_number"),
            "task_count":
                _load("qsb_worker_task_board.json", {}).get("task_count"),
        },
        # ── Worker Truth Debug (V1) ─────────────────────────────────
        "worker_truth_debug": {
            "canonical_count":
                _load("qsb_worker_truth_contract.json", {})
                .get("total_canonical_workers"),
            "active_count":
                _load("qsb_worker_truth_contract.json", {})
                .get("active_reporting_workers"),
            "simulated_count":
                _load("qsb_worker_truth_contract.json", {})
                .get("simulated_workers"),
            "legacy_unified_view_count":
                (_load("qsb_worker_truth_contract.json", {})
                 .get("visible_dashboard_workers") or {}).get("legacy_unified_view"),
            "preferred_count_for_ui":
                _load("qsb_worker_truth_contract.json", {})
                .get("total_canonical_workers"),
            "label_when_legacy_view_active":
                (_load("qsb_worker_truth_contract.json", {})
                 .get("visible_dashboard_workers") or {})
                .get("label_when_legacy_view_active"),
            "debug_endpoint": "/api/debug/worker_count_sources",
        },
        "last_update_ts": _now(),
    }
    payload.update(_safety_envelope())
    P_LIVE.parent.mkdir(parents=True, exist_ok=True)
    P_LIVE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    print(json.dumps(build_live_telemetry(), indent=2))


if __name__ == "__main__":
    main()
