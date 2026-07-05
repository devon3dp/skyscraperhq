"""Tower Audit V1 — runs the full 15-category battery + scoring + history."""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe
from .audit_checks import CATEGORY_FUNCS, SEVERITY_WEIGHTS

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LATEST_PATH  = ROOT / "state/tower_ops/audit_latest.json"
HISTORY_PATH = ROOT / "state/tower_ops/audit_history.json"
LOG_PATH     = ROOT / "logs/tower_ops/full_audit.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _category_score(rows):
    if not rows: return 0
    weights = [SEVERITY_WEIGHTS.get(r["severity"], 0.0) for r in rows]
    avg = sum(weights) / len(weights)
    return max(0, min(100, int(round(avg * 100))))


def run_full(payload=None):
    with _LOCK:
        results_by_cat = {}
        critical = []; warnings = []; failures = []
        for name, fn in CATEGORY_FUNCS:
            try:
                rows = fn()
            except Exception as exc:
                rows = [{"severity": "FAIL", "code": name + "_exception",
                          "message": str(exc)[:200], "ts": _now()}]
            results_by_cat[name] = rows
            for r in rows:
                if r["severity"] == "CRITICAL": critical.append({"category": name, **r})
                elif r["severity"] == "FAIL":   failures.append({"category": name, **r})
                elif r["severity"] == "WARN":   warnings.append({"category": name, **r})
        category_scores = {k: _category_score(v) for k, v in results_by_cat.items()}
        overall_score = int(round(sum(category_scores.values()) / max(1, len(category_scores))))
        overall_status = ("critical" if critical else "warning" if warnings else "healthy")
        report = {
            "ok": True, "ts": _now(),
            "phase": "QSB_TOWER_OPERATIONS_V3",
            "overall_status": overall_status,
            "overall_score": overall_score,
            "category_scores": category_scores,
            "critical_failures": critical,
            "failures": failures,
            "warnings": warnings,
            "results_by_category": results_by_cat,
            **LOCKED_FALSE,
        }
        LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        # Append to history
        hist = {"history": []}
        if HISTORY_PATH.exists():
            try: hist = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception: pass
        hist.setdefault("history", []).append({
            "ts": report["ts"], "overall_status": overall_status,
            "overall_score": overall_score,
            "critical_count": len(critical), "fail_count": len(failures),
            "warn_count": len(warnings),
        })
        hist["history"] = hist["history"][-50:]
        hist.update(LOCKED_FALSE); hist["ts"] = _now()
        HISTORY_PATH.write_text(json.dumps(hist, indent=2), encoding="utf-8")
        # Audit log line
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": report["ts"], "overall_status": overall_status,
                                 "overall_score": overall_score,
                                 "critical_count": len(critical),
                                 "execution_allowed": False}) + "\n")
        return stamp_safe(report)


def latest():
    if not LATEST_PATH.exists():
        return run_full()
    try: return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception: return run_full()


def history():
    if not HISTORY_PATH.exists():
        return stamp_safe({"ok": True, "ts": _now(), "history": []})
    try: return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception: return stamp_safe({"ok": True, "ts": _now(), "history": []})


def status():
    L = latest()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "overall_status": L.get("overall_status"),
        "overall_score":  L.get("overall_score"),
        "category_scores": L.get("category_scores"),
        "critical_count": len(L.get("critical_failures") or []),
        "fail_count":     len(L.get("failures") or []),
        "warn_count":     len(L.get("warnings") or []),
    })


def gaps():
    L = latest()
    out = {"missing_departments": [], "missing_endpoints": [],
            "missing_workers": [], "uncertified_workers": [],
            "broken_routes": [], "not_configured_telemetry": [],
            "unsafe_flags": []}
    for r in L.get("warnings") or []:
        if r.get("code") == "dept_floor_missing":
            out["missing_departments"].append(r["message"])
        if r.get("code") == "lane_missing":
            out["missing_endpoints"].append(r["message"])
        if r.get("code") == "uncertified_sensitive_workers":
            out["uncertified_workers"].append(r["message"])
    for r in L.get("failures") or []:
        out["broken_routes"].append(r["message"])
    for r in L.get("critical_failures") or []:
        out["unsafe_flags"].append(r["message"])
    # not_configured_telemetry pulled from accounts
    try:
        from .accounts_department import not_configured
        out["not_configured_telemetry"] = [x.get("endpoint") for x in (not_configured().get("not_configured") or [])]
    except Exception:
        pass
    return stamp_safe({"ok": True, "ts": _now(), **out})
