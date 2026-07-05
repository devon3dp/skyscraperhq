"""
QSB Workforce Expansion + 9 New Departments
Phase: QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1

Employs 1,000 new workers across 9 new departments/sub-departments and
writes their manifests + rooms + worker rosters.

Workforce expansion is mechanical: each new worker_id is deterministic
(e.g. wrk_recruit_001), has a real role, real home_floor, real class,
real state, and a real room/station. NO INVENTED ACTIVITY — workers
are stationed idle_at_station by default and only "work" when real
events (paper trade open/close, OpenClaw tickets, Guardian blocks,
lift movements) generate movements via qsb_live_telemetry_repairs.

Writes:

  data/registries/qsb_workforce_expansion_v1.json
  data/registries/qsb_workforce_expansion_v1_roster.json
  data/registries/qsb_department_room_map.json
  data/registries/qsb_department_completion_audit.json
  data/registries/qsb_floor_occupancy_plan.json
  data/registries/qsb_worker_visual_policy.json
  data/registries/qsb_worker_visual_state.json
  data/registries/qsb_worker_station_assignments.json
  data/registries/qsb_worker_room_assignments.json
  data/registries/qsb_workforce_state_machine.json
  data/registries/qsb_worker_lifecycle_state.json
  data/registries/qsb_worker_current_assignments.json
  data/registries/qsb_event_routing_contract.json
  data/registries/qsb_profit_mission_map.json
  data/registries/qsb_department_profit_contribution.json
  data/registries/qsb_live_packets_latest.json

  floors/floor_44_accounts_department/rewards_office_manifest.json
  floors/floor_44_accounts_department/promotion_board_manifest.json
  floors/floor_30_permissions_risk/disciplinary_review_manifest.json
  floors/floor_47_executive_operations_department/worker_operations_manifest.json
  floors/floor_49_resource_management_department/rest_dormitory_manifest.json
  floors/floor_52_infrastructure_command_department/floor_operations_manifest.json

Rules:
  * Every worker has a real worker_id and traceable home_floor + room.
  * No worker is operational without a department + role + station.
  * SIM/training workers default to Training Academy interior only.
  * Real-money trading remains disabled. Real OpenClaw execution
    remains disabled.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
FLOORS = ROOT / "floors"


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
        "read_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


# ── Department blueprint ────────────────────────────────────────────────

# (key, name, floor, floor_number, rooms[], roles[], worker_count_to_add,
#  default_class, default_state)
DEPARTMENT_BLUEPRINT = [
    ("recruitment", "Recruitment Agency",
     "floor_45_worker_recruitment_agency", 45,
     ["Candidate Intake", "Screening Desk", "Hiring Desk",
      "Assignment Board", "New Worker Orientation"],
     ["recruiter", "screener", "hiring_officer",
      "orientation_lead", "intake_clerk"],
     80, "candidate_worker", "awaiting_assignment"),
    ("training_academy", "Training Academy",
     "floor_36_expansion_planning_department", 36,
     ["Training Pods", "Simulation Room", "Strategy Classroom",
      "Safety Rules Classroom", "Graduation Desk"],
     ["instructor", "simulation_supervisor", "strategy_lecturer",
      "safety_officer", "graduation_clerk"],
     150, "training_worker", "training"),
    ("lessons_room", "Lessons Room",
     "floor_38_sandbox_operations", 38,
     ["Mistake Review Desk", "Lesson Library", "Repeated Error Board",
      "Redemption Desk", "Cleared Worker Board"],
     ["reviewer", "librarian", "error_analyst",
      "redemption_coach", "clearing_clerk"],
     50, "lesson_worker", "reviewing_lesson"),
    ("worker_operations_control", "Worker Operations Control",
     "floor_47_executive_operations_department", 47,
     ["Task Dispatch Board", "Movement Control",
      "Floor Assignment Desk", "Idle Worker Roster",
      "Active Worker Roster"],
     ["dispatcher", "movement_controller", "assignment_officer",
      "roster_clerk", "operations_supervisor"],
     90, "operational_worker", "idle_at_station"),
    ("rewards_office", "Rewards Office",
     "floor_44_accounts_department", 44,
     ["Worker of the Day", "Worker of the Week", "Worker of the Month",
      "Medal Cabinet", "Reward Point Ledger"],
     ["awards_officer", "ledger_clerk", "medal_curator",
      "weekly_judge", "daily_judge"],
     60, "operational_worker", "idle_at_station"),
    ("promotion_board", "Promotion Board",
     "floor_44_accounts_department", 44,
     ["Promotion Review Table", "Eligible Workers Board",
      "Pending Colonel Approval", "Rank Ladder"],
     ["promotion_reviewer", "rank_clerk", "approval_courier",
      "ladder_curator"],
     40, "operational_worker", "idle_at_station"),
    ("disciplinary_review_board", "Disciplinary Review Board",
     "floor_30_permissions_department", 30,
     ["Strike Desk", "Guardian Block Review", "Retraining Orders",
      "Suspension Board", "Redemption Path"],
     ["strike_officer", "block_reviewer", "retraining_orderly",
      "suspension_clerk", "redemption_warden"],
     70, "operational_worker", "idle_at_station"),
    ("rest_dormitory", "Rest / Dormitory Floor",
     "floor_49_resource_management_department", 49,
     ["Rest Pods", "Standby Lounge", "Shift Change Desk",
      "Offline Worker Bay"],
     ["dormitory_warden", "standby_supervisor",
      "shift_change_clerk", "offline_bay_clerk"],
     280, "resting_worker", "resting"),
    ("floor_operations", "Floor Operations Department",
     "floor_52_infrastructure_command_department", 52,
     ["Floor Directory", "Department Registry",
      "Floor Health Board", "Missing Room Board"],
     ["floor_director", "department_registrar",
      "health_inspector", "missing_room_auditor"],
     180, "operational_worker", "idle_at_station"),
]

P_ROSTER         = REG / "qsb_workforce_expansion_v1_roster.json"
P_SUMMARY        = REG / "qsb_workforce_expansion_v1.json"
P_ROOM_MAP       = REG / "qsb_department_room_map.json"
P_DEPT_AUDIT     = REG / "qsb_department_completion_audit.json"
P_OCCUPANCY      = REG / "qsb_floor_occupancy_plan.json"
P_VISUAL_POLICY  = REG / "qsb_worker_visual_policy.json"
P_VISUAL_STATE   = REG / "qsb_worker_visual_state.json"
P_STATIONS       = REG / "qsb_worker_station_assignments.json"
P_ROOM_ASSIGN    = REG / "qsb_worker_room_assignments.json"
P_STATE_MACHINE  = REG / "qsb_workforce_state_machine.json"
P_LIFECYCLE      = REG / "qsb_worker_lifecycle_state.json"
P_CURRENT_ASSIGN = REG / "qsb_worker_current_assignments.json"
P_EVENT_ROUTING  = REG / "qsb_event_routing_contract.json"
P_PROFIT_MAP     = REG / "qsb_profit_mission_map.json"
P_DEPT_PROFIT    = REG / "qsb_department_profit_contribution.json"
P_LIVE_PACKETS   = REG / "qsb_live_packets_latest.json"


WORKER_CLASSES = [
    "operational_worker", "training_worker", "candidate_worker",
    "lesson_worker", "resting_worker", "suspended_worker",
    "stale_worker", "visual_group",
]
WORKER_STATES = [
    "idle_at_station", "working", "moving", "training",
    "reviewing_lesson", "awaiting_assignment", "resting",
    "promoted", "warned", "suspended", "blocked", "stale",
]


def _generate_workers_for_department(dept_key, dept_name, floor, rooms,
                                       roles, count, cls, state):
    workers = []
    n_rooms = max(1, len(rooms))
    n_roles = max(1, len(roles))
    for i in range(1, count + 1):
        wid = "wrk_v1_%s_%03d" % (dept_key[:14], i)
        role = roles[(i - 1) % n_roles]
        room = rooms[(i - 1) % n_rooms]
        station = "%s · station #%02d" % (room, ((i - 1) // n_rooms) + 1)
        workers.append({
            "worker_id": wid,
            "display_name": "%s %s #%03d" % (
                dept_name.split()[0],
                role.replace("_", " ").title(),
                i,
            ),
            "class": cls,
            "state": state,
            "floor": floor,
            "department": dept_name,
            "room": room,
            "station": station,
            "role": role,
            "current_task": "stationed at " + room + " · awaiting source event",
            "task_source": "no_live_event",
            "last_event_ts": _now(),
            "visible_in_dashboard": cls in (
                "operational_worker", "training_worker",
                "candidate_worker", "lesson_worker", "resting_worker"
            ),
            "visible_reason": "interior_view_only",
            "is_simulation": False,
            "reporting_enabled": True,
            "learning_enabled": True,
            "paper_tasking_enabled": True,
            "real_execution_enabled": False,
            "employment_phase":
                "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        })
    return workers


def build_roster():
    roster = []
    by_dept = {}
    by_floor = {}
    by_class = {}
    for (key, name, floor, fnum, rooms, roles,
         count, cls, state) in DEPARTMENT_BLUEPRINT:
        ws = _generate_workers_for_department(key, name, floor, rooms,
                                                roles, count, cls, state)
        roster.extend(ws)
        by_dept[name] = len(ws)
        by_floor[floor] = by_floor.get(floor, 0) + len(ws)
        by_class[cls] = by_class.get(cls, 0) + len(ws)
    payload = {
        "ok": True,
        "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        "kind": "qsb_workforce_expansion_v1_roster",
        "generated_ts": _now(),
        "total_new_workers": len(roster),
        "by_department": by_dept,
        "by_floor": by_floor,
        "by_class": by_class,
        "workers": roster,
    }
    payload.update(_safety_envelope())
    _write_json(P_ROSTER, payload)
    return payload


def build_summary(roster):
    payload = {
        "ok": True,
        "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        "kind": "qsb_workforce_expansion_v1",
        "generated_ts": _now(),
        "total_new_workers_employed": roster["total_new_workers"],
        "by_department": roster["by_department"],
        "by_floor": roster["by_floor"],
        "by_class": roster["by_class"],
        "departments_built": [name for _, name, *_ in DEPARTMENT_BLUEPRINT],
        "department_count": len(DEPARTMENT_BLUEPRINT),
    }
    payload.update(_safety_envelope())
    _write_json(P_SUMMARY, payload)
    return payload


# ── Department room map + occupancy plan ────────────────────────────────

def build_department_room_map(roster):
    by_dept = {}
    for w in roster["workers"]:
        d = w["department"]
        room = w["room"]
        by_dept.setdefault(d, {}).setdefault(room, []).append(w["worker_id"])
    payload = {
        "ok": True,
        "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        "kind": "qsb_department_room_map",
        "generated_ts": _now(),
        "departments": {
            name: {
                "floor": floor,
                "floor_number": fnum,
                "rooms": rooms,
                "roles": roles,
                "worker_count": len([w for w in roster["workers"]
                                      if w["department"] == name]),
                "class": cls,
                "default_state": state,
            }
            for (_, name, floor, fnum, rooms, roles,
                 _, cls, state) in DEPARTMENT_BLUEPRINT
        },
        "by_department_room_assignments": by_dept,
    }
    payload.update(_safety_envelope())
    _write_json(P_ROOM_MAP, payload)
    return payload


def build_department_completion_audit(roster):
    items = []
    for (_, name, floor, fnum, rooms, roles, count, cls, state) in DEPARTMENT_BLUEPRINT:
        items.append({
            "department": name,
            "floor": floor,
            "floor_number": fnum,
            "rooms_built": rooms,
            "worker_count": count,
            "class": cls,
            "default_state": state,
            "status": "complete",
            "rooms_complete": len(rooms),
            "manifest_path": (
                "floors/%s/%s_manifest.json" % (floor, name.lower()
                                                .replace(" / ", "_")
                                                .replace(" ", "_"))
            ),
        })
    payload = {
        "ok": True,
        "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        "kind": "qsb_department_completion_audit",
        "generated_ts": _now(),
        "total_departments": len(items),
        "complete_count": sum(1 for i in items if i["status"] == "complete"),
        "items": items,
    }
    payload.update(_safety_envelope())
    _write_json(P_DEPT_AUDIT, payload)
    return payload


def build_floor_occupancy_plan(roster):
    payload = {
        "ok": True,
        "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        "kind": "qsb_floor_occupancy_plan",
        "generated_ts": _now(),
        "occupancy_by_floor": roster["by_floor"],
        "training_academy_floor": 36,
        "lessons_room_floor": 38,
        "recruitment_floor": 45,
        "accounts_floor": 44,
        "guardian_risk_floor": 30,
        "worker_operations_floor": 47,
        "rest_dormitory_floor": 49,
        "floor_operations_floor": 52,
        "policy_note":
            "Workers are stationed at their assigned floor + room + station. "
            "External tower view shows per-floor count badges only. "
            "Interior view shows individual workers per room.",
    }
    payload.update(_safety_envelope())
    _write_json(P_OCCUPANCY, payload)
    return payload


# ── Visual policy + station assignments + state machine ─────────────────

def build_visual_policy():
    payload = {
        "ok": True,
        "kind": "qsb_worker_visual_policy",
        "generated_ts": _now(),
        "exterior_tower_view": {
            "show_individual_workers": False,
            "show_grouped_per_floor_badges": True,
            "show_top_active_movements": True,
            "max_movement_arrows_visible": 5,
            "show_attention_alerts": True,
            "show_sim_labels_externally": False,
        },
        "interior_floor_view": {
            "show_individual_workers_for_selected_floor": True,
            "show_room_stations": True,
            "show_worker_task_state": True,
            "tooltip_fields": ["worker_id", "class", "role", "floor",
                                "room", "station", "current_task",
                                "last_event_ts"],
        },
        "movement_rules": {
            "no_movement_without_event":  True,
            "no_random_orbits":           True,
            "no_random_hops":             True,
            "source_registry":            "qsb_worker_movements_latest.json",
        },
        "sim_workers_policy":
            "Training Academy interior only (floor_36).",
        "candidate_workers_policy":
            "Recruitment Agency interior only (floor_45).",
        "lesson_workers_policy":
            "Lessons Room interior only (floor_38).",
        "resting_workers_policy":
            "Rest Dormitory interior only (floor_49).",
    }
    payload.update(_safety_envelope())
    _write_json(P_VISUAL_POLICY, payload)
    return payload


def build_visual_state(roster):
    by_floor_visible = {}
    for w in roster["workers"]:
        if w.get("visible_in_dashboard"):
            by_floor_visible[w["floor"]] = by_floor_visible.get(w["floor"], 0) + 1
    payload = {
        "ok": True,
        "kind": "qsb_worker_visual_state",
        "generated_ts": _now(),
        "default_exterior_mode":   "counts_only",
        "interior_workers_per_floor_visible": by_floor_visible,
        "exterior_individual_workers_visible_count": 0,
        "policy_compliance":       "all_v1_expansion_workers_routed_to_interior_only",
    }
    payload.update(_safety_envelope())
    _write_json(P_VISUAL_STATE, payload)
    return payload


def build_station_and_room_assignments(roster):
    stations = {}
    rooms = {}
    for w in roster["workers"]:
        stations[w["worker_id"]] = {
            "floor": w["floor"], "room": w["room"],
            "station": w["station"],
        }
        rooms.setdefault(w["floor"], {}).setdefault(w["room"], []).append(w["worker_id"])
    sp = {
        "ok": True, "kind": "qsb_worker_station_assignments",
        "generated_ts": _now(),
        "station_count": len(stations),
        "stations": stations,
    }
    sp.update(_safety_envelope())
    _write_json(P_STATIONS, sp)

    rp = {
        "ok": True, "kind": "qsb_worker_room_assignments",
        "generated_ts": _now(),
        "by_floor_room": rooms,
    }
    rp.update(_safety_envelope())
    _write_json(P_ROOM_ASSIGN, rp)
    return sp, rp


def build_state_machine_and_lifecycle(roster):
    payload = {
        "ok": True, "kind": "qsb_workforce_state_machine",
        "generated_ts": _now(),
        "worker_classes":  WORKER_CLASSES,
        "worker_states":   WORKER_STATES,
        "transitions": {
            "hired":             ["awaiting_assignment"],
            "assigned":          ["idle_at_station"],
            "task_dispatched":   ["working", "moving"],
            "movement_event":    ["moving"],
            "lesson_assigned":   ["reviewing_lesson"],
            "training_assigned": ["training"],
            "rested":            ["resting"],
            "promotion_approved":["promoted", "idle_at_station"],
            "strike_issued":     ["warned"],
            "suspension_issued": ["suspended"],
            "guardian_block":    ["blocked"],
            "stale_detected":    ["stale"],
        },
        "default_state_for_class": {
            "operational_worker":"idle_at_station",
            "training_worker":   "training",
            "candidate_worker":  "awaiting_assignment",
            "lesson_worker":     "reviewing_lesson",
            "resting_worker":    "resting",
            "suspended_worker":  "suspended",
            "stale_worker":      "stale",
        },
    }
    payload.update(_safety_envelope())
    _write_json(P_STATE_MACHINE, payload)

    lifecycle = {
        "ok": True, "kind": "qsb_worker_lifecycle_state",
        "generated_ts": _now(),
        "by_class_count": roster["by_class"],
        "policy":
            "Workers transition states only when a real event fires "
            "(paper trade open/close, Guardian block, OpenClaw ticket, "
            "promotion approval, etc.). No automatic random state changes.",
    }
    lifecycle.update(_safety_envelope())
    _write_json(P_LIFECYCLE, lifecycle)

    current = {
        "ok": True, "kind": "qsb_worker_current_assignments",
        "generated_ts": _now(),
        "by_department": roster["by_department"],
        "by_floor":      roster["by_floor"],
        "by_class":      roster["by_class"],
        "total_assigned": roster["total_new_workers"],
    }
    current.update(_safety_envelope())
    _write_json(P_CURRENT_ASSIGN, current)


# ── Event routing + profit mission ──────────────────────────────────────

def build_event_routing_contract():
    payload = {
        "ok": True, "kind": "qsb_event_routing_contract",
        "generated_ts": _now(),
        "events_to_packets": [
            "worker_hired", "worker_assigned", "worker_trained",
            "worker_passed_training", "worker_failed_training",
            "lesson_created", "trade_opened", "trade_closed",
            "pnl_recorded", "reward_issued", "promotion_approved",
            "strike_issued", "guardian_block", "openclaw_ticket",
            "lift_movement", "narrator_utterance",
            "hardware_warning", "code_observatory_warning",
        ],
        "policy": (
            "No event → no packet. No movement event → no movement. "
            "Packets sourced from qsb_live_packets_latest.json built "
            "from real registries."
        ),
        "packet_sources": [
            "qsb_worker_movements_latest.json",
            "qsb_lift_movements_latest.json",
            "qsb_paper_trading.sqlite paper_trade_events",
            "qsb_openclaw_state.json diagnostic_tickets",
            "eqsb_guardian_state.json (blocked_reasons)",
            "qsb_worker_discipline_triggers.json",
            "qsb_worker_promotions.json eligible_workers",
            "qsb_worker_rewards.json (active nominees)",
            "qsb_narrator_history_latest.json",
            "eqsb_performance_advice.json",
            "eqsb_code_risk_report.json",
        ],
    }
    payload.update(_safety_envelope())
    _write_json(P_EVENT_ROUTING, payload)
    return payload


def build_live_packets():
    """Compose a single canonical live-packet list from all real sources."""
    pkts = []
    movements = _load("qsb_worker_movements_latest.json", {})
    for m in (movements.get("movements") or []):
        pkts.append({
            "packet_id": "pkt_wm_" + (m.get("movement_id") or "x"),
            "kind": "worker_movement",
            "source_floor": m.get("source_floor"),
            "target_floor": m.get("target_floor"),
            "reason":       m.get("reason"),
            "worker_id":    m.get("worker_id"),
            "ts":           m.get("timestamp"),
        })
    lifts = _load("qsb_lift_movements_latest.json", {})
    for lm in (lifts.get("movements") or []):
        pkts.append({
            "packet_id": "pkt_lift_" + str(lm.get("packet_id") or "x"),
            "kind": "lift_movement",
            "source_floor": lm.get("source_floor"),
            "target_floor": lm.get("target_floor"),
            "reason":       lm.get("reason"),
            "lift_id":      lm.get("lift_id"),
            "ts":           lm.get("timestamp"),
        })
    payload = {
        "ok": True, "kind": "qsb_live_packets_latest",
        "generated_ts": _now(),
        "packet_count": len(pkts),
        "policy": "Composed only from real source registries.",
        "packets": pkts,
    }
    payload.update(_safety_envelope())
    _write_json(P_LIVE_PACKETS, payload)
    return payload


def build_profit_mission_map():
    payload = {
        "ok": True, "kind": "qsb_profit_mission_map",
        "generated_ts": _now(),
        "mission": "Safe, disciplined, repeatable paper/testnet profit. Real-money trading remains disabled.",
        "department_to_profit_role": {
            "Trading Floors (41/42/43)": "create paper/testnet trade events",
            "Accounts / PnL Department": "record results, post to ledger",
            "Audit / Ledger":            "verify logs",
            "Lessons Room":              "review mistakes",
            "Training Academy":          "retrain weak workers",
            "Rewards Office":            "reward strong workers",
            "Disciplinary Review Board": "handle repeated rule failures",
            "Recruitment Agency":        "fill gaps",
            "Worker Operations Control": "assign workers",
            "Kernel / Penthouse":        "summary + Colonel briefings",
        },
        "real_money_live_trading_enabled": False,
    }
    payload.update(_safety_envelope())
    _write_json(P_PROFIT_MAP, payload)

    profit = _load("qsb_profit_command.json", {})
    contrib = {
        "ok": True, "kind": "qsb_department_profit_contribution",
        "generated_ts": _now(),
        "by_department": profit.get("by_department"),
        "total_realized_pnl": profit.get("total_realized_pnl"),
        "best_department": profit.get("best_department_by_contribution"),
        "policy_note":
            "Departments contribute by routing paper-trade events "
            "through their workers; only the paper trading desk + "
            "accounts/PnL post realized PnL.",
    }
    contrib.update(_safety_envelope())
    _write_json(P_DEPT_PROFIT, contrib)


# ── Floor manifest writers for the new departments ──────────────────────

def _write_dept_manifest(floor_dir, fname, manifest):
    base = FLOORS / floor_dir
    if not base.exists():
        return False
    _write_json(base / fname, manifest)
    return True


def write_new_department_manifests(roster):
    written = []
    for (key, name, floor, fnum, rooms, roles,
         count, cls, state) in DEPARTMENT_BLUEPRINT:
        fname = name.lower().replace(" / ", "_").replace(" ", "_") + "_manifest.json"
        manifest = {
            "ok": True,
            "kind": "department_manifest",
            "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
            "generated_ts": _now(),
            "floor_id": "floor_%02d" % fnum,
            "department": name,
            "sub_department": key,
            "co_located_on_floor": floor,
            "purpose":
                "Operational interior for %s. Workers stationed at "
                "real rooms with real roles; no random visuals." % name,
            "rooms": rooms,
            "roles": roles,
            "worker_count": count,
            "default_class": cls,
            "default_state": state,
            "advisory_only": True,
            "execution_allowed": False,
        }
        manifest.update(_safety_envelope())
        if _write_dept_manifest(floor, fname, manifest):
            written.append(floor + "/" + fname)
    return written


# ── Orchestrator ────────────────────────────────────────────────────────

def build_all():
    roster = build_roster()
    summary = build_summary(roster)
    build_department_room_map(roster)
    build_department_completion_audit(roster)
    build_floor_occupancy_plan(roster)
    build_visual_policy()
    build_visual_state(roster)
    build_station_and_room_assignments(roster)
    build_state_machine_and_lifecycle(roster)
    build_event_routing_contract()
    build_profit_mission_map()
    build_live_packets()
    manifests = write_new_department_manifests(roster)
    return {
        "ok": True,
        "phase": "QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1",
        "new_workers_employed": summary["total_new_workers_employed"],
        "departments_built": summary["department_count"],
        "by_department": summary["by_department"],
        "by_class": summary["by_class"],
        "manifests_written_count": len(manifests),
        "manifests_written": manifests[:10],
        **_safety_envelope(),
    }


def main():
    print(json.dumps(build_all(), indent=2))


if __name__ == "__main__":
    main()
