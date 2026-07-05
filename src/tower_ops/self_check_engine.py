"""V2.0 self-check engine — runs a category-by-category audit of the live tower."""

from datetime import datetime, timezone
from pathlib import Path
import json, urllib.request, urllib.error, py_compile

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE = ROOT / "state/tower_ops/self_check_latest.json"
BASE = "http://127.0.0.1:8765"


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure(): STATE.parent.mkdir(parents=True, exist_ok=True)


def _http(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            code = r.status
            try: body = json.loads(r.read().decode("utf-8"))
            except Exception: body = None
            return {"path": path, "code": code, "ok": code == 200, "body": body}
    except Exception as e:
        return {"path": path, "code": None, "ok": False, "error": str(e)[:160]}


def check_audit():
    r = _http("/api/audit/latest")
    return {"category": "audit", "ok": r.get("ok"), "detail": r}


def check_not_working():
    r = _http("/api/tower_ops/not_working")
    items = (r.get("body") or {}).get("items") or []
    warns = sum(1 for i in items if (i.get("severity") or "").upper() == "WARN")
    return {"category": "not_working", "ok": r.get("ok"),
            "items": len(items), "warns": warns}


def check_stale_language():
    r = _http("/api/ui/stale_language_audit")
    files = (r.get("body") or {}).get("files_with_hits") or 0
    return {"category": "stale_language", "ok": r.get("ok"),
            "files_with_hits": files}


def check_floor_activation():
    r = _http("/api/floors/activation_matrix")
    body = (r.get("body") or {})
    return {"category": "floor_activation", "ok": r.get("ok"),
            "active": body.get("active_count"),
            "staged": body.get("staged_count"),
            "vacant": body.get("vacant_count")}


def check_worker_routes():
    r = _http("/api/workers/routes")
    body = (r.get("body") or {})
    routes = body.get("worker_routes") or []
    return {"category": "worker_routes", "ok": r.get("ok"),
            "route_count": len(routes)}


def check_comms():
    r = _http("/api/comms/company")
    body = (r.get("body") or {})
    return {"category": "comms", "ok": r.get("ok"),
            "active_routes": (body.get("active_routes") or 0),
            "message_count": (body.get("message_count") or 0)}


def check_trading_safety():
    r = _http("/api/unified")
    body = r.get("body") or {}
    text = json.dumps(body)
    must_false = [
        "live_trading_enabled", "openclaw_execution_enabled",
        "autonomous_dispatch_enabled", "direct_provider_access",
        "external_provider_execution_enabled", "provider_execution_enabled",
        "binance_live_trading_enabled", "stock_live_trading_enabled",
    ]
    violations = []
    for k in must_false:
        if f'"{k}": true' in text:
            violations.append(k)
    return {"category": "trading_safety",
            "ok": (len(violations) == 0 and r.get("ok")),
            "violations": violations}


def check_gauges():
    r = _http("/api/gauges/all")
    body = r.get("body") or {}
    return {"category": "gauges", "ok": r.get("ok"),
            "gauge_floor_count": len((body.get("by_floor") or {}))}


def check_speech_audio():
    r = _http("/api/speech/status")
    return {"category": "speech_audio", "ok": r.get("ok")}


def check_renderer():
    r = _http("/api/renderer/state")
    return {"category": "renderer", "ok": r.get("ok")}


def check_compile():
    errors = []
    for p in ROOT.glob("src/**/*.py"):
        try: py_compile.compile(str(p), doraise=True)
        except Exception as e: errors.append({"file": str(p), "error": str(e)[:160]})
    return {"category": "compile", "ok": (len(errors) == 0),
            "errors_count": len(errors), "errors": errors[:10]}


def check_test_smoke():
    import subprocess
    samples = [
        "tests/test_lift_network_v12.py",
        "tests/test_floor25_lift_route_v11a.py",
        "tests/test_oanda_paper_strategy_lab_v1.py",
        "tests/test_worker_sandbox_v1.py",
        "tests/test_security_spine_v11.py",
        "tests/test_agent_coordination_v11.py",
    ]
    rows = []
    for t in samples:
        try:
            res = subprocess.run(["python3", t], cwd=str(ROOT),
                                  env={"PYTHONPATH": str(ROOT / "src"),
                                        "PATH": "/usr/bin:/bin"},
                                  capture_output=True, timeout=30)
            rows.append({"test": t, "ok": res.returncode == 0,
                          "code": res.returncode})
        except Exception as e:
            rows.append({"test": t, "ok": False, "error": str(e)[:160]})
    return {"category": "test_smoke",
            "ok": all(r["ok"] for r in rows),
            "pass": sum(1 for r in rows if r["ok"]),
            "fail": sum(1 for r in rows if not r["ok"]),
            "rows": rows}


CHECKS = [
    check_compile, check_audit, check_not_working, check_stale_language,
    check_floor_activation, check_worker_routes, check_comms,
    check_trading_safety, check_gauges, check_speech_audio, check_renderer,
    check_test_smoke,
]


def run_self_check():
    _ensure()
    rows = []
    for fn in CHECKS:
        try: r = fn()
        except Exception as e: r = {"category": fn.__name__, "ok": False, "error": str(e)[:160]}
        rows.append(r)
    out = stamp_safe({
        "ok": True, "ts": _now(),
        "label": "QSB_TOWER_V2_0_SELF_CHECK",
        "category_count": len(rows),
        "categories": rows,
        "pass_count": sum(1 for r in rows if r.get("ok")),
        "fail_count": sum(1 for r in rows if not r.get("ok")),
        "execution_allowed": False,
    })
    STATE.write_text(json.dumps(out, indent=2))
    return out


def latest():
    if STATE.exists():
        try: return json.loads(STATE.read_text())
        except Exception: pass
    return stamp_safe({"ok": False, "status": "no_latest_state"})
