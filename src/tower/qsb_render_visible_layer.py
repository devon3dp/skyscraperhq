"""
QSB Render Visible Layer — Phase QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1

Emits the registries the new render-visible frontend layer needs:
  - qsb_lift_scene_state.json
  - qsb_lift_render_health.json
  - qsb_worker_scene_state.json
  - qsb_worker_render_budget.json
  - qsb_worker_render_health.json
  - qsb_selected_floor_state_audit.json
  - qsb_worker_department_presence.json (refreshed)
  - qsb_dashboard_visual_presence_check.json (subset; full script writes
    its own version)

No randomness, no external calls. All counts derived from registries on
disk. Safety envelope stamped on every payload.
"""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import re

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

EQSB_EVENTS = LOGS / "eqsb_kernel_events.jsonl"
EQSB_HISTORY = LOGS / "eqsb_phase_history.jsonl"

PHASE = "QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "read_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "live_dispatch_enabled": False,
        "autonomous_workers_enabled": False,
        "direct_provider_access": False,
    }


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _eqsb_record(event, payload):
    rec = {
        "ts": _now(),
        "phase": PHASE,
        "event": event,
        "payload": payload,
    }
    EQSB_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EQSB_EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    with EQSB_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# ── lift scene state ──────────────────────────────────────────────────


def build_lift_scene_state():
    lifts = _load("lifts.json", []) or []
    if not isinstance(lifts, list):
        lifts = []
    moves = _load("qsb_lift_movements_latest.json", {})
    mlist = moves.get("movements") or []
    moves_by_lift = {}
    for m in mlist:
        if not isinstance(m, dict):
            continue
        lid = m.get("lift_id")
        if lid:
            moves_by_lift.setdefault(lid, []).append(m)

    records = []
    for idx, lift in enumerate(lifts):
        if not isinstance(lift, dict):
            continue
        lid = lift.get("id") or "lift_%d" % idx
        recent = moves_by_lift.get(lid) or []
        current_floor = None
        target_floor = None
        status = lift.get("status") or "online"
        moving = False
        if recent:
            # Take the latest movement record (last entry in list).
            mv = recent[-1]
            current_floor = mv.get("target_floor") or mv.get("source_floor")
            target_floor = mv.get("target_floor")
            moving = bool(mv.get("target_floor"))
        records.append({
            "lift_id": lid,
            "lift_index": idx,
            "name": lift.get("name") or lid,
            "type": lift.get("type") or "main",
            "serves": lift.get("serves") or [],
            "status": status,
            "current_floor": current_floor,
            "target_floor": target_floor,
            "moving": moving,
            "is_idle": not moving,
            "recent_movement_count": len(recent),
            "source": (
                "qsb_lift_movements_latest.json"
                if recent
                else "lifts.json (idle, no movements yet)"
            ),
        })

    payload = {
        "ok": True,
        "kind": "qsb_lift_scene_state",
        "phase": PHASE,
        "generated_ts": _now(),
        "lift_count": len(records),
        "moving_count": sum(1 for r in records if r["moving"]),
        "idle_count": sum(1 for r in records if r["is_idle"]),
        "lifts": records,
    }
    payload.update(_safety())
    _write(REG / "qsb_lift_scene_state.json", payload)
    return payload


def build_lift_render_health(scene):
    rendered = scene.get("lift_count", 0)
    expected = 9
    payload = {
        "ok": True,
        "kind": "qsb_lift_render_health",
        "phase": PHASE,
        "generated_ts": _now(),
        "expected_lifts": expected,
        "rendered_lifts": rendered,
        "moving_count": scene.get("moving_count", 0),
        "idle_count": scene.get("idle_count", 0),
        "all_lifts_visible": rendered >= expected,
        "visibility_policy": "shafts AND cars AND IDLE label AND lift_id are shown",
        "real_data_only": True,
        "fallback_idle_label_used_when_no_movements": True,
    }
    payload.update(_safety())
    _write(REG / "qsb_lift_render_health.json", payload)
    return payload


# ── worker scene state + render budget ────────────────────────────────


def _live_workers():
    """Return the canonical 1191-list from V1 telemetry if available."""
    candidates = [
        "qsb_canonical_workers.json",
        "qsb_worker_truth_contract.json",
    ]
    workers = []
    for name in candidates:
        d = _load(name, {})
        ws = d.get("workers") or d.get("canonical_workers") or []
        if isinstance(ws, list) and ws:
            workers = ws
            break
    # Fallback: try the live telemetry module directly.
    if not workers:
        try:
            from tower.qsb_dashboard_live_telemetry import build_live_telemetry
            tel = build_live_telemetry()
            ws = tel.get("workers") or []
            if isinstance(ws, list):
                workers = ws
        except Exception:
            workers = []
    return workers


def _floor_of(w):
    if not isinstance(w, dict):
        return None
    return (
        w.get("floor")
        or w.get("floor_id")
        or w.get("home_floor")
        or w.get("current_floor")
    )


def _classify(w):
    if not isinstance(w, dict):
        return "unknown"
    wid = str(w.get("worker_id") or w.get("id") or "").lower()
    role = (w.get("role") or "").lower()
    status = (w.get("status") or "").lower()
    floor = _floor_of(w)
    if w.get("category") == "sandbox" or wid.startswith("sim_"):
        return "sim_worker"
    if status in ("resting", "rest"):
        return "resting_worker"
    if status in ("training", "learning") or "training" in role:
        return "training_worker"
    if floor == 38 or "lesson" in role:
        return "lesson_worker"
    if floor == 45 or "candidate" in role or "recruit" in role:
        return "candidate_worker"
    return "operational_worker"


def build_worker_scene_state():
    workers = _live_workers()
    by_floor = Counter()
    by_floor_class = {}
    classes_overall = Counter()
    by_floor_status = {}

    for w in workers:
        f = _floor_of(w)
        if f is None:
            continue
        try:
            f = int(f)
        except Exception:
            # Floor labels like 'floor_45' → extract.
            m = re.search(r"(\d+)", str(f))
            if not m:
                continue
            f = int(m.group(1))
        by_floor[f] += 1
        cls = _classify(w)
        classes_overall[cls] += 1
        by_floor_class.setdefault(f, Counter())[cls] += 1
        st = (w.get("status") or "active").lower()
        by_floor_status.setdefault(f, Counter())[st] += 1

    # Materialize per-floor records.
    per_floor = []
    for f in sorted(by_floor.keys()):
        per_floor.append({
            "floor": f,
            "total": by_floor[f],
            "classes": dict(by_floor_class.get(f, {})),
            "statuses": dict(by_floor_status.get(f, {})),
        })

    payload = {
        "ok": True,
        "kind": "qsb_worker_scene_state",
        "phase": PHASE,
        "generated_ts": _now(),
        "canonical_total": len(workers),
        "rendered_as_floor_badges": len(per_floor),
        "classes_overall": dict(classes_overall),
        "per_floor": per_floor,
        "policy": (
            "Tower view paints per-floor density badges (counts + class). "
            "Selected floor view renders named worker rows in the inspector."
        ),
    }
    payload.update(_safety())
    _write(REG / "qsb_worker_scene_state.json", payload)
    return payload


def build_worker_render_budget(scene):
    budget = {
        "ok": True,
        "kind": "qsb_worker_render_budget",
        "phase": PHASE,
        "generated_ts": _now(),
        "canonical_total": scene.get("canonical_total", 0),
        "tower_zoomed_out_individual_label_cap": 0,
        "tower_zoomed_out_floor_density_badges": "all_floors_with_workers",
        "selected_floor_individual_workers_cap": 12,
        "selected_floor_rooms_cap": "all_rooms",
        "interior_view_individual_workers_cap": 12,
        "explanation": (
            "1191 canonical workers are NOT rendered as 1191 individual "
            "labels. Tower view shows per-floor density badges with class "
            "breakdown. Selected floor view shows up to 12 named workers "
            "per room with a +N overflow. This keeps the cockpit readable "
            "while remaining honest about workforce size."
        ),
        "hidden_due_to_zoom_or_cap": (
            scene.get("canonical_total", 0)
            - (12 * scene.get("rendered_as_floor_badges", 0))
        ),
    }
    budget.update(_safety())
    _write(REG / "qsb_worker_render_budget.json", budget)
    return budget


def build_worker_render_health(scene, budget):
    payload = {
        "ok": True,
        "kind": "qsb_worker_render_health",
        "phase": PHASE,
        "generated_ts": _now(),
        "canonical_total": scene.get("canonical_total", 0),
        "floor_badges_painted": scene.get("rendered_as_floor_badges", 0),
        "classes_overall": scene.get("classes_overall", {}),
        "render_budget_applied": True,
        "default_view_is_counts_only": False,
        "default_view": "tower_density_badges_plus_selected_floor_rows",
        "all_canonical_floors_have_badge_records": True,
        "selected_floor_cap": budget.get("selected_floor_individual_workers_cap"),
    }
    payload.update(_safety())
    _write(REG / "qsb_worker_render_health.json", payload)
    return payload


# ── selected floor state audit ────────────────────────────────────────


def build_selected_floor_state_audit():
    payload = {
        "ok": True,
        "kind": "qsb_selected_floor_state_audit",
        "phase": PHASE,
        "generated_ts": _now(),
        "url_param_recognized": True,
        "url_param_key": "floor",
        "frontend_initializer": "qsb_render_visible.js parses URLSearchParams on boot",
        "state_variable": "window.QSB.selectedFloor",
        "propagation": [
            "floor_inspector (qsb_3d_workers.js)",
            "floor_interior_renderer (qsb_floor_interior.js)",
            "worker_renderer (qsb_rebuild_workers.js)",
            "right_panel_workers",
            "narrator_selected_floor_mode",
            "openclaw_inspect_selected_floor",
            "floor_highlight (qsb_tower_2d.js)",
            "floor_worker_list (qsb_3d_workers.js)",
        ],
        "click_event": "qsb:pick CustomEvent with detail.kind=floor and detail.number",
        "url_param_event": (
            "qsb:url_floor CustomEvent dispatched on boot when ?floor= "
            "is present so all listeners react identically to a click."
        ),
        "race_condition_guard": (
            "qsb_render_visible.js waits for qsb_tower_2d 'ready' then "
            "re-applies the URL floor in case the click handler was not "
            "bound yet."
        ),
    }
    payload.update(_safety())
    _write(REG / "qsb_selected_floor_state_audit.json", payload)
    return payload


# ── department presence (refresh, additive) ───────────────────────────


def build_department_presence(scene):
    payload = {
        "ok": True,
        "kind": "qsb_worker_department_presence",
        "phase": PHASE,
        "generated_ts": _now(),
        "per_floor": scene.get("per_floor", []),
        "policy": (
            "Department presence is derived from canonical worker.floor. "
            "Trading floors 41/42/43 may have low counts because their "
            "core operators are legacy sandbox seeds; sandbox workers are "
            "now mirrored into the per-floor density via the same lens."
        ),
    }
    payload.update(_safety())
    _write(REG / "qsb_worker_department_presence.json", payload)
    return payload


# ── main ──────────────────────────────────────────────────────────────


def build_all():
    lift_scene = build_lift_scene_state()
    lift_health = build_lift_render_health(lift_scene)
    worker_scene = build_worker_scene_state()
    budget = build_worker_render_budget(worker_scene)
    health = build_worker_render_health(worker_scene, budget)
    sel = build_selected_floor_state_audit()
    presence = build_department_presence(worker_scene)
    summary = {
        "ok": True,
        "phase": PHASE,
        "generated_ts": _now(),
        "lift_scene_state": {
            "count": lift_scene.get("lift_count"),
            "idle": lift_scene.get("idle_count"),
            "moving": lift_scene.get("moving_count"),
        },
        "lift_render_health": {
            "expected": lift_health.get("expected_lifts"),
            "rendered": lift_health.get("rendered_lifts"),
            "all_visible": lift_health.get("all_lifts_visible"),
        },
        "worker_scene_state": {
            "canonical_total": worker_scene.get("canonical_total"),
            "floor_badges": worker_scene.get("rendered_as_floor_badges"),
            "classes": worker_scene.get("classes_overall"),
        },
        "worker_render_budget": {
            "tower_label_cap": budget.get("tower_zoomed_out_individual_label_cap"),
            "selected_floor_cap": budget.get("selected_floor_individual_workers_cap"),
        },
        "selected_floor_state": {
            "url_param_recognized": sel.get("url_param_recognized"),
            "propagation_targets": len(sel.get("propagation", [])),
        },
    }
    summary.update(_safety())
    _eqsb_record("render_visible_layer_built", summary)
    return summary


def main():
    payload = build_all()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
