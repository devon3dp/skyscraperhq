"""V2.0 autonomous company loop — chains self-check, self-fix, final acceptance."""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe
from . import self_check_engine as SCE
from . import self_fix_engine as SFE
from . import final_acceptance as FAE

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE = ROOT / "state/tower_ops/autonomous_company_loop.json"
LOG_PATH = ROOT / "logs/tower_ops/autonomous_company_loop.jsonl"

MAX_PASSES = 7


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append_log(rec):
    _ensure()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "ts": _now()}) + "\n")


def status():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "AUTONOMOUS_COMPANY_LOOP_STATUS",
        "max_passes": MAX_PASSES,
        "state_exists": STATE.exists(),
        "execution_allowed": False,
    })


def run_once(payload=None):
    _append_log({"event": "run_once_start"})
    check = SCE.run_self_check()
    fix   = SFE.run_self_fix()
    accept = FAE.evaluate()
    out = stamp_safe({
        "ok": True, "ts": _now(),
        "label": "AUTONOMOUS_COMPANY_LOOP_RUN_ONCE",
        "self_check": check,
        "self_fix":   fix,
        "final_acceptance": accept,
        "execution_allowed": False,
    })
    _ensure()
    STATE.write_text(json.dumps(out, indent=2))
    _append_log({"event": "run_once_complete",
                  "pass_count": check.get("pass_count"),
                  "fail_count": check.get("fail_count"),
                  "score": accept.get("score"),
                  "accepted": accept.get("accepted")})
    return out


def run_until_acceptance(payload=None):
    _append_log({"event": "run_until_acceptance_start"})
    passes = []
    accepted = False
    last_score = -1
    for i in range(1, MAX_PASSES + 1):
        r = run_once(payload)
        accept = r.get("final_acceptance") or {}
        score = accept.get("score", 0)
        passes.append({"pass": i, "score": score,
                        "accepted": accept.get("accepted"),
                        "pass_count": (r.get("self_check") or {}).get("pass_count"),
                        "fail_count": (r.get("self_check") or {}).get("fail_count")})
        if accept.get("accepted"):
            accepted = True; break
        # If no improvement, stop early
        if score <= last_score and i > 1:
            break
        last_score = score
    final = stamp_safe({
        "ok": True, "ts": _now(),
        "label": "AUTONOMOUS_COMPANY_LOOP_RUN_UNTIL_ACCEPTANCE",
        "passes_completed": len(passes),
        "passes": passes,
        "final_accepted": accepted,
        "final_state": json.loads(STATE.read_text()) if STATE.exists() else None,
        "execution_allowed": False,
    })
    _append_log({"event": "run_until_acceptance_complete",
                  "passes_completed": len(passes), "final_accepted": accepted})
    return final


def latest():
    if STATE.exists():
        try: return json.loads(STATE.read_text())
        except Exception: pass
    return stamp_safe({"ok": False, "status": "no_state"})


def final_acceptance():
    return FAE.evaluate()
