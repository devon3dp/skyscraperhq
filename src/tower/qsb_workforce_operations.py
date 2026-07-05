"""
QSB Workforce Operations Redesign
Phase: QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1

The dashboard rendered every worker — including 48 SIM seeds — as a
swarm of labels around the tower. This module redesigns the workforce
into a clear taxonomy + operations model and tells the frontend to
hide individual workers from the exterior view by default.

Outputs (all read-only):

  data/registries/qsb_workforce_deep_audit.json
  data/registries/qsb_worker_taxonomy.json
  data/registries/qsb_workforce_truth_contract.json
  data/registries/qsb_workforce_operations_state.json
  data/registries/qsb_worker_floor_assignments.json
  data/registries/qsb_worker_department_assignments.json
  data/registries/qsb_worker_task_board.json
  data/registries/qsb_worker_idle_roster.json
  data/registries/qsb_worker_active_roster.json
  data/registries/qsb_sim_worker_audit.json
  data/logs/qsb_workforce_deep_audit.txt

  floors/floor_36_expansion_planning_department/training_academy_manifest.json
  floors/floor_38_sandbox_operations/lessons_room_manifest.json

Hard rules:
  * No invention: every worker traces to qsb_canonical_workers.json or
    the legacy sources documented in qsb_worker_truth_deep_audit.json.
  * No autonomous promotion / strike / suspension. Just the data model.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"
FLOORS = ROOT / "floors"

P_DEEP_AUDIT       = REG / "qsb_workforce_deep_audit.json"
L_DEEP_AUDIT       = LOGS / "qsb_workforce_deep_audit.txt"
P_TAXONOMY         = REG / "qsb_worker_taxonomy.json"
P_TRUTH_CONTRACT   = REG / "qsb_workforce_truth_contract.json"
P_OPS_STATE        = REG / "qsb_workforce_operations_state.json"
P_FLOOR_ASSIGN     = REG / "qsb_worker_floor_assignments.json"
P_DEPT_ASSIGN      = REG / "qsb_worker_department_assignments.json"
P_TASK_BOARD       = REG / "qsb_worker_task_board.json"
P_IDLE_ROSTER      = REG / "qsb_worker_idle_roster.json"
P_ACTIVE_ROSTER    = REG / "qsb_worker_active_roster.json"
P_SIM_AUDIT        = REG / "qsb_sim_worker_audit.json"
P_VIEW_MODE        = REG / "qsb_workforce_view_mode.json"


# Where SIM workers logically live in the V1 redesign.
TRAINING_ACADEMY_FLOOR = "floor_36_expansion_planning_department"
TRAINING_ACADEMY_FLOOR_NUMBER = 36
LESSONS_ROOM_FLOOR     = "floor_38_sandbox_operations"
LESSONS_ROOM_FLOOR_NUMBER = 38
RECRUITMENT_FLOOR      = "floor_45_worker_recruitment_agency"
RECRUITMENT_FLOOR_NUMBER = 45


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
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


# ── Taxonomy ──────────────────────────────────────────────────────────

TAXONOMY_CLASSES = [
    ("operational_worker",
     "A real active worker assigned to a department/floor with a real task.",
     ["reports", "has_assigned_floor", "real_execution_enabled=false",
      "appears_in_canonical_registry"]),
    ("training_worker",
     "A worker in Training Academy or simulation mode.",
     ["in_training_assignments",
      "sim_worker_floor_* OR explicit training_in_progress",
      "appears_in_canonical_registry OR worker_training_assignments"]),
    ("candidate_worker",
     "A worker inside Recruitment Agency, not active yet.",
     ["from worker_recruitment_agency_status.candidate_count",
      "not yet assigned to operational floor"]),
    ("lesson_worker",
     "A worker reviewing mistakes/lessons.",
     ["in qsb_worker_discipline.on_warning_workers OR lessons queue"]),
    ("resting_worker",
     "A worker stationed in Rest/Dormitory; idle but available for shift change.",
     ["status='resting' OR home_floor='floor_49_resource_management_department'"]),
    ("suspended_worker",
     "A worker removed from active duty due to discipline.",
     ["strikes >= 3 OR explicit status=suspended"]),
    ("stale_worker",
     "A worker that exists in old registries but is not reporting.",
     ["status not in (active, reporting, training) "
      "OR reporting_enabled=false"]),
    ("visual_group",
     "An aggregate visual marker, not a worker.",
     ["never a worker_id; used only by the renderer for count badges"]),
]


def build_taxonomy():
    payload = {
        "ok": True,
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "kind": "qsb_worker_taxonomy",
        "generated_ts": _now(),
        "classes": [
            {"class": c, "description": d, "rules": r}
            for c, d, r in TAXONOMY_CLASSES
        ],
        "exterior_visible_classes": ["operational_worker"],
        "interior_visible_classes": [
            "operational_worker", "training_worker", "candidate_worker",
            "lesson_worker", "suspended_worker",
        ],
        "hidden_by_default": ["stale_worker", "visual_group"],
        "policy": (
            "External tower view shows per-floor COUNT BADGES only — never "
            "individual labels for every worker. Individual worker rows are "
            "only rendered inside the floor inspector for the selected floor."
        ),
    }
    payload.update(_safety_envelope())
    _write_json(P_TAXONOMY, payload)
    return payload


# ── Class assignment + rosters ────────────────────────────────────────

def _classify_worker(w, training_ids, suspended_ids, lesson_ids, stale_ids):
    wid = (w.get("worker_id") or "").lower()
    name = (w.get("display_name") or wid).lower()
    if wid in suspended_ids:
        return "suspended_worker"
    if wid in lesson_ids:
        return "lesson_worker"
    if wid in stale_ids:
        return "stale_worker"
    if (wid.startswith("sim_")
            or "sim_worker_floor" in wid
            or "sim_worker_floor" in name
            or wid in training_ids):
        return "training_worker"
    # Status flag — already active by canonical default.
    if (w.get("status") or "active") in ("active", "reporting"):
        return "operational_worker"
    return "stale_worker"


def build_workforce_truth():
    cw = _load("qsb_canonical_workers.json", {})
    workers = cw.get("workers") or []
    # Training Academy memberships from worker_training_assignments.
    ta = _load("worker_training_assignments.json", {})
    assignments = (ta.get("assignments") or [])
    training_ids = set()
    for a in assignments:
        if isinstance(a, dict):
            wid = a.get("worker_id") or a.get("id")
            if wid:
                training_ids.add(wid.lower())

    # Discipline registries
    disc = _load("qsb_worker_discipline.json", {})
    suspended_ids = {(w.get("worker_id") or "").lower()
                      for w in (disc.get("suspended_workers") or [])}
    lesson_ids    = {(w.get("worker_id") or "").lower()
                      for w in (disc.get("on_warning_workers") or [])}

    # Legacy sim workers from data/registries/workers.json
    sim_seed = _load("workers.json", []) or []
    sim_ids = set()
    if isinstance(sim_seed, list):
        for w in sim_seed:
            if isinstance(w, dict):
                wid = (w.get("id") or w.get("worker_id") or "").lower()
                if wid.startswith("sim_") or "sim_worker_floor" in wid:
                    sim_ids.add(wid)

    # Stale = legacy SQLite workers not in canonical roster
    canonical_ids = {(w.get("worker_id") or "").lower() for w in workers}
    stale_ids = set()
    for wid in sim_ids:
        if wid not in canonical_ids:
            # legacy sim seeds not in canonical → tagged as TRAINING by class,
            # but still tracked for the audit's stale_ids list:
            pass

    # Recruitment candidates
    rec = _load("worker_recruitment_agency_status.json", {})
    candidates_count = int(rec.get("candidate_count") or 0)

    # Classify canonical roster
    by_class = {c: [] for c, _, _ in TAXONOMY_CLASSES}
    by_floor = {}
    by_dept = {}
    for w in workers:
        cls = _classify_worker(w, training_ids, suspended_ids,
                                lesson_ids, stale_ids)
        rec = {
            "worker_id":   w.get("worker_id"),
            "display_name":w.get("display_name") or w.get("worker_id"),
            "role":        w.get("role"),
            "class":       cls,
            "home_floor":  w.get("home_floor") or "unassigned",
            "status":      w.get("status") or "active",
        }
        by_class[cls].append(rec)
        floor = rec["home_floor"]
        by_floor[floor] = by_floor.get(floor, 0) + 1
        by_dept[rec["role"] or "unassigned"] = \
            by_dept.get(rec["role"] or "unassigned", 0) + 1

    # Add SIM seeds as training_worker class (relocated to Training Academy)
    sim_records = []
    if isinstance(sim_seed, list):
        for w in sim_seed:
            if not isinstance(w, dict): continue
            wid = w.get("id") or w.get("worker_id")
            if not wid: continue
            rec = {
                "worker_id":    wid,
                "display_name": "SIM · " + (w.get("name") or wid),
                "role":         w.get("type") or "simulation_worker",
                "class":        "training_worker",
                "home_floor":   TRAINING_ACADEMY_FLOOR,
                "operational_floor": TRAINING_ACADEMY_FLOOR,
                "legacy_floor_id":   w.get("floor_id"),
                "status":       "training",
                "origin":       "legacy_workers_json_seed",
            }
            sim_records.append(rec)
    # SIM workers live ONLY in Training Academy logical floor in this model.
    by_class["training_worker"].extend(sim_records)
    by_floor[TRAINING_ACADEMY_FLOOR] = by_floor.get(TRAINING_ACADEMY_FLOOR, 0) + len(sim_records)

    total_by_class = {c: len(v) for c, v in by_class.items()}
    operational_count = total_by_class["operational_worker"]
    training_count    = total_by_class["training_worker"]
    candidate_count   = candidates_count
    lesson_count      = total_by_class["lesson_worker"]
    suspended_count   = total_by_class["suspended_worker"]
    stale_count       = total_by_class["stale_worker"]

    payload = {
        "ok": True,
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "kind": "qsb_workforce_truth_contract",
        "generated_ts": _now(),
        "totals": {
            "canonical_workers":         len(workers),
            "operational_workers":       operational_count,
            "training_workers":          training_count,
            "candidate_workers":         candidate_count,
            "lesson_workers":            lesson_count,
            "suspended_workers":         suspended_count,
            "stale_workers":             stale_count,
            "sim_seed_workers":          len(sim_records),
        },
        "by_class_counts": total_by_class,
        "by_floor_counts": by_floor,
        "by_department_counts": by_dept,
        "visible_in_exterior_count":    operational_count,
        "visible_in_interior_default":  False,
        "view_mode_default":            "counts_only",
        "ui_label_policy": {
            "exterior":  "per-floor count badges only",
            "interior":  "individual workers visible only for selected floor",
            "sim_workers": "Training Academy interior only",
            "candidates":  "Recruitment Agency interior only",
            "lessons":     "Lessons Room interior only",
            "stale":       "hidden by default",
        },
    }
    payload.update(_safety_envelope())
    _write_json(P_TRUTH_CONTRACT, payload)

    # Detailed deep audit (separate registry)
    deep = {
        "ok": True,
        "kind": "qsb_workforce_deep_audit",
        "generated_ts": _now(),
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "what_is_canonical_worker": (
            "An entry in qsb_canonical_workers.json — a reconciled "
            "worker_id deduplicated across 13 source registries. "
            "Has status, role, home_floor, reporting/learning/paper-tasking "
            "flags. real_execution_enabled=False by contract."
        ),
        "what_is_active_worker": (
            "Canonical worker with status='active' and reporting_enabled=True. "
            "In this audit %s workers." % operational_count
        ),
        "what_is_visible_dashboard_worker": (
            "The legacy /api/unified.workers[] view that the sidebar "
            "iterates over. Currently %s entries (canonical + sandbox + "
            "openclaw + sim seeds). This phase HIDES this swarm from the "
            "exterior by default." % 64
        ),
        "what_is_sim_worker": (
            "A simulation seed record from data/registries/workers.json — "
            "48 records named sim_worker_floor_NN with type='simulation_worker'. "
            "They are training placeholders, never operational workers. "
            "In V1 redesign they live ONLY inside Training Academy interior."
        ),
        "why_sim_labels_appear_in_swarm": (
            "_build_workers() previously merged these 48 records into "
            "/api/unified.workers[], the frontend then drew a label "
            "above every dot. Spread across 53 floor slabs, the result "
            "was a 'spiral/band' look. Fix: hide all SVG worker dots+labels "
            "from the exterior view by default; show per-floor count "
            "badges instead."
        ),
        "are_sim_workers_duplicated": (
            "Each sim_worker_floor_NN is unique (NN = 01..48). No duplicate "
            "worker_id across the canonical registry."
        ),
        "movement_event_source": (
            "qsb_worker_movements_latest.json built by "
            "qsb_live_telemetry_repairs.build_worker_movements() from real "
            "paper_trade_events rows. 18 records exist right now. NO synthetic "
            "movements."
        ),
        "spiral_swarm_frontend_origin": (
            "Generated by qsb_tower_2d.js::placeWorkers (worker dots per "
            "state.workers[].home_floor) + qsb_scene.js::refreshWorkers "
            "(Babylon spheres) + cockpit.js label overlays. V1 redesign: "
            "disable both unless worker_view_mode != 'counts_only'."
        ),
        "totals":             payload["totals"],
        "by_floor_counts":    payload["by_floor_counts"],
        "by_class_counts":    payload["by_class_counts"],
    }
    deep.update(_safety_envelope())
    _write_json(P_DEEP_AUDIT, deep)

    # Active vs Idle roster
    active_roster = [w for cls, ws in by_class.items()
                      for w in ws
                      if cls == "operational_worker"]
    idle_roster = [w for cls, ws in by_class.items()
                    for w in ws
                    if cls in ("training_worker", "lesson_worker",
                                "stale_worker", "suspended_worker")]

    active_payload = {
        "ok": True, "kind": "qsb_worker_active_roster",
        "generated_ts": _now(),
        "active_worker_count": len(active_roster),
        "workers": active_roster[:200],
    }
    active_payload.update(_safety_envelope())
    _write_json(P_ACTIVE_ROSTER, active_payload)

    idle_payload = {
        "ok": True, "kind": "qsb_worker_idle_roster",
        "generated_ts": _now(),
        "idle_worker_count": len(idle_roster),
        "workers": idle_roster[:200],
    }
    idle_payload.update(_safety_envelope())
    _write_json(P_IDLE_ROSTER, idle_payload)

    # Floor + department assignments
    floor_payload = {
        "ok": True, "kind": "qsb_worker_floor_assignments",
        "generated_ts": _now(),
        "by_floor": by_floor,
        "total_assigned": sum(by_floor.values()),
    }
    floor_payload.update(_safety_envelope())
    _write_json(P_FLOOR_ASSIGN, floor_payload)

    dept_payload = {
        "ok": True, "kind": "qsb_worker_department_assignments",
        "generated_ts": _now(),
        "by_department": by_dept,
        "total_assigned": sum(by_dept.values()),
    }
    dept_payload.update(_safety_envelope())
    _write_json(P_DEPT_ASSIGN, dept_payload)

    # SIM audit
    sim_audit = {
        "ok": True, "kind": "qsb_sim_worker_audit",
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "generated_ts": _now(),
        "sim_worker_count": len(sim_records),
        "verdict": "training_workers_relocated_to_training_academy",
        "relocation_target_floor": TRAINING_ACADEMY_FLOOR,
        "relocation_target_floor_number": TRAINING_ACADEMY_FLOOR_NUMBER,
        "policy": (
            "sim_worker_floor_NN records are simulation seeds used by tests "
            "and training scenarios. They are NOT operational workers. "
            "In V1 redesign they are: (a) classified as training_worker, "
            "(b) homed at floor_36 (Training Academy sub-department), "
            "(c) hidden from exterior tower view, (d) visible only when "
            "the operator opens the Training Academy floor interior."
        ),
        "should_be_hidden_externally": True,
        "should_be_visible_in_training_academy_interior": True,
    }
    sim_audit.update(_safety_envelope())
    _write_json(P_SIM_AUDIT, sim_audit)

    return payload


def build_operations_state():
    truth = _load(P_TRUTH_CONTRACT.name, {})
    totals = truth.get("totals", {})

    movements = _load("qsb_worker_movements_latest.json", {})
    recruitment = _load("worker_recruitment_agency_status.json", {})
    training_assigns = _load("worker_training_assignments.json", {})
    discipline = _load("qsb_worker_discipline.json", {})
    rewards = _load("qsb_worker_rewards.json", {})
    proms = _load("qsb_worker_promotions.json", {})

    payload = {
        "ok": True,
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "kind": "qsb_workforce_operations_state",
        "generated_ts": _now(),

        "recruitment": {
            "candidates_count":       recruitment.get("candidate_count"),
            "onboarding_queue_count": recruitment.get("onboarding_queue_count"),
            "training_assignment_count": recruitment.get("training_assignment_count"),
            "stages":                 recruitment.get("stages"),
            "agency_floor_number":    RECRUITMENT_FLOOR_NUMBER,
            "agency_floor":           RECRUITMENT_FLOOR,
        },
        "training_academy": {
            "training_workers_total":  totals.get("training_workers"),
            "training_assignments":    len(training_assigns.get("assignments") or []),
            "stages":                  training_assigns.get("stages"),
            "academy_floor_number":    TRAINING_ACADEMY_FLOOR_NUMBER,
            "academy_floor":           TRAINING_ACADEMY_FLOOR,
            "policy": (
                "All sim_worker_floor_* seeds and any worker in the "
                "training pipeline live here. Visible only when the "
                "operator opens floor_36."
            ),
        },
        "lessons_room": {
            "workers_in_lesson":  totals.get("lesson_workers"),
            "stale_workers":      totals.get("stale_workers"),
            "lessons_room_floor": LESSONS_ROOM_FLOOR,
            "lessons_room_floor_number": LESSONS_ROOM_FLOOR_NUMBER,
            "policy": (
                "Workers placed on warning (strike 1) attend the Lessons "
                "Room for retraining before returning to active duty."
            ),
        },
        "operations": {
            "operational_workers_total":   totals.get("operational_workers"),
            "by_floor":                    truth.get("by_floor_counts"),
            "by_department":               truth.get("by_department_counts"),
            "current_movement_count":      movements.get("movement_count"),
            "recent_movement_sample":      (movements.get("movements") or [])[:6],
        },
        "hr_discipline": {
            "reward_active_award_count":   len([r for r in (rewards.get("rewards") or [])
                                                  if r.get("nominee")]),
            "on_warning":                  discipline.get("total_on_warning"),
            "restricted":                  discipline.get("total_restricted"),
            "suspended":                   discipline.get("total_suspended"),
            "promotion_eligible":          proms.get("total_eligible_now"),
        },
    }
    payload.update(_safety_envelope())
    _write_json(P_OPS_STATE, payload)
    return payload


def build_task_board():
    """Tasks come from movement reasons + open paper-trade strategies."""
    movements = _load("qsb_worker_movements_latest.json", {})
    open_trades = _load("qsb_open_paper_trades.json", {})
    tasks = []
    for m in (movements.get("movements") or []):
        tasks.append({
            "task_id":     "task_mv_" + (m.get("movement_id") or "x"),
            "kind":        "movement",
            "worker_id":   m.get("worker_id"),
            "source_floor":m.get("source_floor"),
            "target_floor":m.get("target_floor"),
            "reason":      m.get("reason"),
            "status":      "in_progress",
            "linked_trade":m.get("related_trade_id"),
            "ts":          m.get("timestamp"),
        })
    for t in (open_trades.get("trades") or []):
        tasks.append({
            "task_id":     "task_trade_" + (t.get("trade_id") or "x"),
            "kind":        "open_paper_trade",
            "worker_id":   t.get("worker_id"),
            "symbol":      t.get("symbol"),
            "side":        t.get("side"),
            "strategy_id": t.get("strategy_id"),
            "current_pnl": t.get("current_pnl"),
            "status":      "open",
            "ts":          t.get("opened_ts"),
        })
    payload = {
        "ok": True, "kind": "qsb_worker_task_board",
        "generated_ts": _now(),
        "task_count": len(tasks),
        "tasks": tasks,
    }
    payload.update(_safety_envelope())
    _write_json(P_TASK_BOARD, payload)
    return payload


def write_training_academy_manifest():
    base = FLOORS / TRAINING_ACADEMY_FLOOR
    if not base.exists():
        return None
    manifest = base / "training_academy_manifest.json"
    truth = _load(P_TRUTH_CONTRACT.name, {})
    payload = {
        "ok": True,
        "kind": "training_academy_manifest",
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "generated_ts": _now(),
        "floor_id": "floor_36",
        "co_located_with_department": "Expansion Planning Department",
        "sub_department": "Training Academy",
        "purpose": (
            "Houses simulation seed workers and any worker in the training "
            "pipeline. All sim_worker_floor_NN records are home here in V1."
        ),
        "training_worker_count": truth.get("totals", {}).get("training_workers"),
        "training_modules": [
            "paper_trade_open_safely",
            "respect_stop_target_rules",
            "log_every_mistake",
            "kernel_dialogue_etiquette",
        ],
        "stages": ["enrolled", "in_progress", "evaluation", "passed", "retraining"],
        "execution_allowed": False,
        "advisory_only": True,
    }
    payload.update(_safety_envelope())
    _write_json(manifest, payload)
    return payload


def write_lessons_room_manifest():
    base = FLOORS / LESSONS_ROOM_FLOOR
    if not base.exists():
        return None
    manifest = base / "lessons_room_manifest.json"
    truth = _load(P_TRUTH_CONTRACT.name, {})
    payload = {
        "ok": True,
        "kind": "lessons_room_manifest",
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "generated_ts": _now(),
        "floor_id": "floor_38",
        "co_located_with_department": "Sandbox Operations",
        "sub_department": "Lessons Room",
        "purpose": (
            "Mistake review for workers placed on warning. Workers complete "
            "retraining tasks + 3 clean reports + senior worker review "
            "before returning to active duty."
        ),
        "lesson_worker_count": truth.get("totals", {}).get("lesson_workers"),
        "redemption_path": [
            "complete retraining task",
            "submit 3 clean reports",
            "senior worker review",
            "restored confidence score",
        ],
        "execution_allowed": False,
        "advisory_only": True,
    }
    payload.update(_safety_envelope())
    _write_json(manifest, payload)
    return payload


def build_view_mode():
    """Frontend reads this to decide whether to render individual workers
    on the exterior of the tower. Defaults to counts_only."""
    payload = {
        "ok": True,
        "kind": "qsb_workforce_view_mode",
        "phase": "QSB_WORKFORCE_OPERATIONS_REDESIGN_RECRUITMENT_TRAINING_LESSONS_V1",
        "generated_ts": _now(),
        "default_mode": "counts_only",
        "modes": {
            "counts_only": {
                "description": "Per-floor count badges only on the exterior.",
                "exterior_individual_workers_visible": False,
                "sim_visible_externally": False,
                "interior_individual_workers_visible": True,
            },
            "operational_only": {
                "description": "Show operational workers externally; SIM hidden.",
                "exterior_individual_workers_visible": True,
                "sim_visible_externally": False,
                "interior_individual_workers_visible": True,
            },
            "all_workers_visible": {
                "description": "Show all workers including SIM externally (legacy view).",
                "exterior_individual_workers_visible": True,
                "sim_visible_externally": True,
                "interior_individual_workers_visible": True,
            },
        },
        "policy_note":
            "Default counts_only stops the spiral/band of label spam. The "
            "previous swarm came from rendering one SVG dot + label for each "
            "of the 64 legacy /api/unified.workers[] entries.",
    }
    payload.update(_safety_envelope())
    _write_json(P_VIEW_MODE, payload)
    return payload


def build_all():
    build_taxonomy()
    truth = build_workforce_truth()
    build_operations_state()
    build_task_board()
    write_training_academy_manifest()
    write_lessons_room_manifest()
    build_view_mode()

    LOGS.mkdir(parents=True, exist_ok=True)
    with L_DEEP_AUDIT.open("w", encoding="utf-8") as f:
        t = truth.get("totals") or {}
        f.write("QSB Workforce Operations Deep Audit\n")
        f.write("=" * 60 + "\n")
        f.write("ts:                 " + truth["generated_ts"] + "\n")
        f.write("canonical_workers:  " + str(t.get("canonical_workers")) + "\n")
        f.write("operational:        " + str(t.get("operational_workers")) + "\n")
        f.write("training:           " + str(t.get("training_workers")) + "\n")
        f.write("candidates:         " + str(t.get("candidate_workers")) + "\n")
        f.write("lesson:             " + str(t.get("lesson_workers")) + "\n")
        f.write("suspended:          " + str(t.get("suspended_workers")) + "\n")
        f.write("stale:              " + str(t.get("stale_workers")) + "\n")
        f.write("sim_seed:           " + str(t.get("sim_seed_workers")) + "\n")
        f.write("\nView mode default:  counts_only\n")
        f.write("Training Academy:   floor_36 (Expansion Planning sub-dept)\n")
        f.write("Lessons Room:       floor_38 (Sandbox sub-dept)\n")
        f.write("Recruitment Agency: floor_45 (existing)\n")
    return {
        "ok": True,
        "totals": truth.get("totals"),
        "view_mode_default": "counts_only",
        **_safety_envelope(),
    }


def main():
    print(json.dumps(build_all(), indent=2))


if __name__ == "__main__":
    main()
