"""Correction loop — audit → fix → recompile → reaudit, bounded passes."""

from datetime import datetime, timezone
from pathlib import Path
import json

from . import correction_actions as CA
from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_LATEST  = ROOT / "state/tower_ops/correction_loop_latest.json"
STATE_HISTORY = ROOT / "state/tower_ops/correction_loop_history.json"
LOG_PATH      = ROOT / "logs/tower_ops/correction_loop.jsonl"

MAX_PASSES = 5


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure_dirs():
    STATE_LATEST.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append_log(rec):
    _ensure_dirs()
    rec = dict(rec); rec.setdefault("ts", _now())
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _persist(result):
    _ensure_dirs()
    STATE_LATEST.write_text(json.dumps(result, indent=2))
    history = []
    if STATE_HISTORY.exists():
        try:
            history = json.loads(STATE_HISTORY.read_text())
        except Exception:
            history = []
    history.append(result)
    history = history[-25:]
    STATE_HISTORY.write_text(json.dumps(history, indent=2))


def _categorize():
    """Read /api/tower_ops/not_working and audit gaps to categorize issues."""
    issues = []
    try:
        from .not_working import report as _nw
        nw = _nw() or {}
        for it in (nw.get("items") or []):
            sev = (it.get("severity") or "").upper()
            kind = "warn" if sev == "WARN" else "info"
            issues.append({"item": it.get("item"), "status": it.get("status"),
                            "severity": sev, "kind": kind})
    except Exception as e:
        issues.append({"item": "not_working_report_failed",
                        "status": str(e)[:160], "severity": "FAIL", "kind": "critical"})
    try:
        from .tower_audit import latest as _al
        al = _al() or {}
        for cat in (al.get("categories") or []):
            for f in (cat.get("findings") or []):
                if f.get("severity") in ("WARN", "FAIL", "CRITICAL"):
                    issues.append({"item": f.get("title"),
                                    "status": f.get("detail"),
                                    "severity": f.get("severity"),
                                    "kind": "audit"})
    except Exception:
        pass
    return issues


def _safe_actions_pass():
    """Run all safe corrective actions once. Returns the action results list."""
    actions = [
        CA.archive_dashboard_backups,
        CA.archive_tower_backups,
        CA.archive_registry_backups,
        CA.archive_static_backups,
        CA.archive_duplicate_floor_shells,
        CA.reconcile_penthouse_kernel_policy,
        CA.promote_security_gate,
        CA.write_archive_manifest,
        CA.py_compile_dashboard,
    ]
    results = []
    for fn in actions:
        try:
            r = fn(); r["ok"] = True
        except Exception as e:
            r = {"action": fn.__name__, "ok": False, "error": str(e)[:240]}
        results.append(r)
        _append_log({"event": "action_complete", "result": r})
    return results


def _endpoint_smoke_test():
    import urllib.request, urllib.error
    base = "http://127.0.0.1:8765"
    paths = [
        "/api/correction/status",
        "/api/tower_ops/not_working",
        "/api/workers/directory",
        "/api/lifts/status",
        "/api/lifts/permission_audit",
        "/api/security/enforcement_status",
        "/api/trading/oanda/live_dashboard",
        "/api/trading/binance/live_dashboard",
        "/api/trading/stocks/live_dashboard",
    ]
    results = []
    for p in paths:
        try:
            req = urllib.request.Request(base + p)
            with urllib.request.urlopen(req, timeout=8) as resp:
                code = resp.status
                body_first = resp.read(800).decode("utf-8", errors="ignore")
            results.append({"path": p, "code": code,
                             "ok": (code == 200),
                             "snippet": body_first[:200]})
        except urllib.error.HTTPError as he:
            results.append({"path": p, "code": he.code, "ok": False,
                             "error": str(he)[:160]})
        except Exception as e:
            results.append({"path": p, "code": None, "ok": False,
                             "error": str(e)[:160]})
    return results


def run_once(payload=None):
    """One full correction pass: categorize → apply safe → recompile → smoke."""
    _append_log({"event": "run_once_start"})
    before = _categorize()
    actions = _safe_actions_pass()
    after = _categorize()
    smoke = _endpoint_smoke_test()
    delta = max(0, len(before) - len(after))
    inventory = CA.collect_safe_corrections_inventory()
    result = stamp_safe({
        "ok": True, "ts": _now(),
        "label": "QSB_TOWER_V1_5_CORRECTION_LOOP_AND_WORKER_VOICE",
        "pass": 1,
        "issues_before":      len(before),
        "issues_after":       len(after),
        "issues_resolved":    delta,
        "actions_applied":    actions,
        "endpoint_smoke":     smoke,
        "issues_remaining":   after,
        "safe_to_apply_inventory": inventory,
        "execution_allowed":  False,
    })
    _persist(result)
    _append_log({"event": "run_once_complete",
                  "issues_before": len(before),
                  "issues_after":  len(after)})
    return result


def run_until_clean(payload=None):
    """Repeat run_once up to MAX_PASSES times, stopping when no progress."""
    _append_log({"event": "run_until_clean_start"})
    passes = []
    last_remaining = None
    for i in range(1, MAX_PASSES + 1):
        r = run_once(payload)
        r["pass"] = i
        passes.append({"pass": i,
                        "issues_before": r["issues_before"],
                        "issues_after":  r["issues_after"]})
        if r["issues_after"] == 0:
            break
        if last_remaining is not None and r["issues_after"] >= last_remaining:
            # No progress; stop to avoid useless work.
            break
        last_remaining = r["issues_after"]
    final = stamp_safe({
        "ok": True, "ts": _now(),
        "label": "QSB_TOWER_V1_5_CORRECTION_LOOP_RUN_UNTIL_CLEAN",
        "passes_completed": len(passes),
        "passes": passes,
        "final_state": json.loads(STATE_LATEST.read_text()) if STATE_LATEST.exists() else None,
        "execution_allowed": False,
    })
    _append_log({"event": "run_until_clean_complete",
                  "passes_completed": len(passes)})
    return final


def status():
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "CORRECTION_LOOP_STATUS",
                        "loop_module": "tower_ops.correction_loop",
                        "max_passes_per_run_until_clean": MAX_PASSES,
                        "state_latest_exists": STATE_LATEST.exists(),
                        "state_history_exists": STATE_HISTORY.exists(),
                        "log_exists": LOG_PATH.exists(),
                        "execution_allowed": False})


def latest():
    if STATE_LATEST.exists():
        try:
            return json.loads(STATE_LATEST.read_text())
        except Exception:
            pass
    return stamp_safe({"ok": False, "status": "no_latest_state",
                        "execution_allowed": False})


def history():
    if STATE_HISTORY.exists():
        try:
            return stamp_safe({"ok": True, "ts": _now(),
                                "history": json.loads(STATE_HISTORY.read_text()),
                                "execution_allowed": False})
        except Exception:
            pass
    return stamp_safe({"ok": True, "ts": _now(), "history": [],
                        "execution_allowed": False})


def actions_inventory():
    return stamp_safe({"ok": True, "ts": _now(),
                        **CA.collect_safe_corrections_inventory(),
                        "execution_allowed": False})
