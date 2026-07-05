"""Certification Engine — issues/revokes/queries worker certifications.

A certification is ADVISORY metadata. It NEVER unlocks execution.
It augments a worker's badge with `certified_for_actions` + `certified_for_floors`.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid

from .safety_contract import LOCKED_FALSE, stamp_safe
from .curriculum_registry import courses, required_for, SENSITIVE_ROLE_GATES


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CERT_PATH = ROOT / "state/tower_ops/worker_certifications.json"
LESS_PATH = ROOT / "state/tower_ops/lesson_records.json"
LOG_PATH  = ROOT / "logs/tower_ops/certification_events.jsonl"
TRAIN_LOG = ROOT / "logs/tower_ops/training_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _read(path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default


def _write(path, data):
    data["ts"] = _now()
    data.update(LOCKED_FALSE)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_log(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now())
    rec.setdefault("execution_allowed", False)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _baseline_certs():
    return {"registry": "qsb_worker_certifications_v1",
            "phase": "QSB_TOWER_OPERATIONS_V3", "ts": _now(),
            "by_worker_id": {}, **LOCKED_FALSE}


def _baseline_lessons():
    return {"registry": "qsb_lesson_records_v1",
            "phase": "QSB_TOWER_OPERATIONS_V3", "ts": _now(),
            "records": [], **LOCKED_FALSE}


# ── Seed initial certifications based on role/team ─────────────────────
def _seed_if_empty():
    certs = _read(CERT_PATH, _baseline_certs())
    if certs.get("by_worker_id"):
        return certs
    # Seed from current worker registry
    try:
        from .worker_registry import workers as worker_list
        ws = (worker_list().get("workers") or [])
    except Exception:
        return certs
    by = {}
    for w in ws:
        wid = w.get("id")
        if not wid: continue
        team = w.get("team") or w.get("department_id") or "general"
        stage = w.get("recruitment_stage") or w.get("stage") or "active_advisory"
        # Auto-grant QSB Induction + Worker Badge & Identity to every active worker
        granted = ["qsb_induction", "worker_badge_identity"]
        if stage in ("active_advisory", "active_read_only", "ready_for_openclaw_review"):
            granted.append("safety_locks_101")
        # Role-based grants — match team to course bundle
        team_to_role = {
            "trading_fx":         "trading_floor_worker",
            "trading_crypto":     "trading_floor_worker",
            "trading_equities":   "trading_floor_worker",
            "accounts":           "accounts_worker",
            "openclaw_advisory":  "openclaw_ready",
            "security":           "security_worker",
            "maintenance":        "maintenance_worker",
            "it_networking":      "it_worker",
            "quantum":            "quantum_worker",
            "airllm_advisory":    "airllm_worker",
            "research_facility":  "research_worker",
            "model_ops":          "model_ops_worker",
        }
        role = team_to_role.get(team)
        if role:
            for cid in required_for(role):
                if cid not in granted: granted.append(cid)
        # Penthouse staff get kernel + speech
        if team == "penthouse_staff":
            granted += ["kernel_communication", "speech_media_controls"]
        granted = list(dict.fromkeys(granted))
        by[wid] = {
            "worker_id": wid,
            "badge_id":  w.get("badge_id"),
            "display_name": w.get("display_name"),
            "training_status": "certified" if "safety_locks_101" in granted else "induction_only",
            "current_course":  None,
            "completed_courses": granted,
            "failed_checks": [],
            "certifications":  [{"course_id": c, "issued_ts": _now(),
                                  "issued_by": "auto_seed_v3"} for c in granted],
            "certified_for_actions": _actions_for(granted),
            "certified_for_floors":  _floors_for(granted, w),
            "next_lesson": None,
            "last_training_ts": _now(),
            "restricted_until_certified": [],
        }
    certs["by_worker_id"] = by
    _write(CERT_PATH, certs)
    return certs


def _actions_for(granted):
    out = set()
    for cid in granted:
        if cid == "safety_locks_101":          out.add("read_lock_matrix")
        if cid == "trading_telemetry_readonly":out.add("read_trading_telemetry")
        if cid == "oanda_telemetry_reading":   out.add("access_floor_41")
        if cid == "binance_telemetry_reading": out.add("access_floor_42")
        if cid == "stocks_telemetry_reading":  out.add("access_floor_43")
        if cid == "accounts_pnl_labels":       out.add("access_accounts_data")
        if cid == "openclaw_readiness_not_exec": out.add("openclaw_readiness_review")
        if cid == "security_permissions":      out.add("security_role")
        if cid == "maintenance_monitoring":    out.add("maintenance_role")
        if cid == "it_local_sidecars":         out.add("it_role")
        if cid == "research_quality_sources":  out.add("research_role")
        if cid == "model_lane_routing":        out.add("read_model_lanes")
        if cid == "airllm_advisory_use":       out.add("airllm_manual_query")
        if cid == "quantum_safety_lab":        out.add("access_quantum_floor")
        if cid == "kernel_communication":      out.add("kernel_chat_use")
        if cid == "speech_media_controls":     out.add("speech_media_use")
        if cid == "manager_reporting":         out.add("manager_role")
        if cid == "overseer_duties":           out.add("overseer_role")
        if cid == "emergency_procedure":       out.add("emergency_role")
    return sorted(out)


def _floors_for(granted, w):
    out = set([w.get("floor_assignment")])
    if "oanda_telemetry_reading" in granted:   out.add("floor_41")
    if "binance_telemetry_reading" in granted: out.add("floor_42")
    if "stocks_telemetry_reading" in granted:  out.add("floor_43")
    if "accounts_pnl_labels" in granted:       out.add("floor_44")
    if "quantum_safety_lab" in granted:        out.add("floor_45")
    if "security_permissions" in granted:      out.add("floor_28")
    if "maintenance_monitoring" in granted:    out.add("floor_33")
    if "it_local_sidecars" in granted:         out.add("floor_35")
    if "kernel_communication" in granted:      out.add("penthouse")
    out.discard(None)
    return sorted(out)


# ── Public API ─────────────────────────────────────────────────────────
def status():
    with _LOCK:
        certs = _seed_if_empty()
        by = certs.get("by_worker_id") or {}
        certified = sum(1 for v in by.values() if v.get("training_status") == "certified")
        uncertified_sensitive = []
        try:
            from .worker_registry import workers as worker_list
            ws = (worker_list().get("workers") or [])
        except Exception:
            ws = []
        for w in ws:
            team = w.get("team")
            rec = by.get(w.get("id")) or {}
            grant = set(rec.get("completed_courses") or [])
            needed = set()
            if team in ("trading_fx","trading_crypto","trading_equities"): needed |= set(required_for("trading_floor_worker"))
            if team == "openclaw_advisory":  needed |= set(required_for("openclaw_ready"))
            if team == "security":           needed |= set(required_for("security_worker"))
            if team == "accounts":           needed |= set(required_for("accounts_worker"))
            if team == "quantum":            needed |= set(required_for("quantum_worker"))
            if team == "airllm_advisory":    needed |= set(required_for("airllm_worker"))
            if not (needed - grant): continue  # fully covered
            uncertified_sensitive.append({
                "worker_id": w.get("id"), "display_name": w.get("display_name"),
                "team": team, "missing": sorted(needed - grant),
            })
        return stamp_safe({
            "ok": True, "ts": _now(),
            "phase": "QSB_TOWER_OPERATIONS_V3",
            "academy_floor": "floor_08",
            "total_worker_records":  len(by),
            "certified_count":       certified,
            "uncertified_count":     len(by) - certified,
            "uncertified_sensitive_count": len(uncertified_sensitive),
            "uncertified_sensitive_workers": uncertified_sensitive[:30],
            "courses_count": len((courses().get("courses") or [])),
        })


def certifications():
    with _LOCK:
        certs = _seed_if_empty()
        return stamp_safe({"ok": True, "ts": _now(),
                            "by_worker_id": certs.get("by_worker_id") or {}})


def enrol(payload):
    payload = payload or {}; wid = payload.get("worker_id"); cid = payload.get("course_id")
    if not wid or not cid: return {"ok": False, "error": "worker_id + course_id required"}
    with _LOCK:
        certs = _seed_if_empty()
        rec = certs.get("by_worker_id", {}).get(wid)
        if not rec: return {"ok": False, "error": "worker_not_found"}
        rec["current_course"] = cid; rec["next_lesson"] = cid
        rec["training_status"] = "in_training"
        rec["last_training_ts"] = _now()
        _write(CERT_PATH, certs)
        _append_log(TRAIN_LOG, {"event": "enrol", "worker_id": wid, "course_id": cid})
        return stamp_safe({"ok": True, "ts": _now(), "worker_id": wid, "course_id": cid})


def complete_lesson(payload):
    payload = payload or {}; wid = payload.get("worker_id"); cid = payload.get("course_id")
    if not wid or not cid: return {"ok": False, "error": "worker_id + course_id required"}
    with _LOCK:
        certs = _seed_if_empty()
        rec = certs.get("by_worker_id", {}).get(wid)
        if not rec: return {"ok": False, "error": "worker_not_found"}
        comp = list(rec.get("completed_courses") or [])
        if cid not in comp: comp.append(cid)
        rec["completed_courses"] = comp
        rec["current_course"] = None
        rec["last_training_ts"] = _now()
        rec["certified_for_actions"] = _actions_for(comp)
        _write(CERT_PATH, certs)
        _append_log(TRAIN_LOG, {"event": "complete_lesson", "worker_id": wid, "course_id": cid})
        return stamp_safe({"ok": True, "ts": _now(), "worker_id": wid, "course_id": cid})


def certify_worker(payload):
    payload = payload or {}; wid = payload.get("worker_id"); cid = payload.get("course_id")
    if not wid or not cid: return {"ok": False, "error": "worker_id + course_id required"}
    with _LOCK:
        certs = _seed_if_empty()
        rec = certs.get("by_worker_id", {}).get(wid)
        if not rec: return {"ok": False, "error": "worker_not_found"}
        rec.setdefault("certifications", []).append({
            "course_id": cid, "issued_ts": _now(), "issued_by": payload.get("issued_by") or "manual",
        })
        comp = list(rec.get("completed_courses") or [])
        if cid not in comp: comp.append(cid)
        rec["completed_courses"] = comp
        rec["training_status"] = "certified"
        rec["certified_for_actions"] = _actions_for(comp)
        _write(CERT_PATH, certs)
        _append_log(LOG_PATH, {"event": "certify_worker", "worker_id": wid, "course_id": cid,
                                 "execution_allowed": False})
        return stamp_safe({"ok": True, "ts": _now(), "worker_id": wid, "course_id": cid,
                            "execution_allowed": False})


def revoke_certification(payload):
    payload = payload or {}; wid = payload.get("worker_id"); cid = payload.get("course_id")
    if not wid or not cid: return {"ok": False, "error": "worker_id + course_id required"}
    with _LOCK:
        certs = _seed_if_empty()
        rec = certs.get("by_worker_id", {}).get(wid)
        if not rec: return {"ok": False, "error": "worker_not_found"}
        rec["certifications"] = [c for c in (rec.get("certifications") or []) if c.get("course_id") != cid]
        rec["completed_courses"] = [c for c in (rec.get("completed_courses") or []) if c != cid]
        rec["certified_for_actions"] = _actions_for(rec["completed_courses"])
        rec["restricted_until_certified"] = sorted(set((rec.get("restricted_until_certified") or []) + [cid]))
        _write(CERT_PATH, certs)
        _append_log(LOG_PATH, {"event": "revoke_certification", "worker_id": wid, "course_id": cid})
        return stamp_safe({"ok": True, "ts": _now(), "worker_id": wid, "course_id": cid})


def worker_training_record(wid):
    with _LOCK:
        return _seed_if_empty().get("by_worker_id", {}).get(wid) or {}
