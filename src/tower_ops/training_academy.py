"""Training Academy — Floor 8 School."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe
from .curriculum_registry import courses, course_count
from .certification_engine import status as cert_status


def _now(): return datetime.now(timezone.utc).isoformat()


CLASSROOMS = [
    "Reception / Intake Desk",
    "Classrooms",
    "Simulation Classroom",
    "Access Badge Classroom",
    "Safety and Locks Classroom",
    "Trading Telemetry Classroom",
    "OpenClaw Readiness Classroom",
    "Research Methods Classroom",
    "IT / Networking Classroom",
    "Security Classroom",
    "Maintenance Classroom",
    "Accounts Classroom",
    "Quantum Classroom",
    "Kernel Etiquette Classroom",
    "Exam Room",
    "Certification Board",
    "Graduation Desk",
    "Training Manager Office",
    "Training Overseer Balcony",
    "Training Accountant Card",
]


def status():
    c = cert_status()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "department": "QSB Training Academy / School",
        "floor_number": 8, "floor_id": "floor_08",
        "phase": "QSB_TOWER_OPERATIONS_V3",
        "academy_name": "QSB Training Academy",
        "classrooms": CLASSROOMS,
        "course_count": course_count(),
        "total_worker_records":    c["total_worker_records"],
        "certified_count":         c["certified_count"],
        "uncertified_count":       c["uncertified_count"],
        "uncertified_sensitive_count": c["uncertified_sensitive_count"],
        "overall_status": "healthy",
        "policy": "ADVISORY_ONLY — courses + certifications never enable execution",
    })


def trained_workers():
    """Return all workers whose training has been recorded."""
    from .certification_engine import certifications
    by = (certifications().get("by_worker_id") or {})
    rows = []
    for wid, rec in by.items():
        rows.append({
            "worker_id":  wid,
            "badge_id":   rec.get("badge_id"),
            "display_name": rec.get("display_name"),
            "training_status": rec.get("training_status"),
            "completed_courses": rec.get("completed_courses") or [],
            "certifications":    rec.get("certifications") or [],
            "certified_for_actions": rec.get("certified_for_actions") or [],
            "certified_for_floors":  rec.get("certified_for_floors") or [],
            "last_training_ts": rec.get("last_training_ts"),
        })
    return stamp_safe({"ok": True, "ts": _now(),
                        "workers_total": len(rows),
                        "workers": rows[:200]})
