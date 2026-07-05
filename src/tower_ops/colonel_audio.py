"""Colonel audio observer — spoken briefing summarizing tower state."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def briefing():
    parts = []
    top_alerts, active_floors, active_workers = [], [], 0
    try:
        from .worker_registry import status as ws
        d = ws() or {}
        active_workers = d.get("total_workers", 0)
    except Exception: pass
    try:
        from .colonel_observation import observation
        ob = observation() or {}
        top_alerts = (ob.get("top_alerts") or [])[:5]
        active_floors = (ob.get("active_floors") or [])[:5]
    except Exception: pass
    open_practice = 0; account_balance = None
    try:
        from .oanda_practice_trading import account, open_trades
        a = account() or {}
        if a.get("ok"):
            account_balance = a.get("balance")
        open_practice = len(open_trades().get("trades") or [])
    except Exception: pass
    pending_approvals = 0
    try:
        from .approval_workflow import pending as pend
        pending_approvals = len(pend().get("pending") or [])
    except Exception: pass
    not_working_warn = 0
    try:
        from .not_working import report as nw
        d = nw() or {}
        not_working_warn = d.get("missing_count", 0)
    except Exception: pass
    correction_pass = "no correction loop result yet"
    try:
        from .correction_loop import latest as cl_latest
        cll = cl_latest() or {}
        if cll.get("ok"):
            correction_pass = (f"last correction pass resolved {cll.get('issues_resolved', 0)} "
                                f"issue(s), {cll.get('issues_after', 0)} remaining")
    except Exception: pass
    security_locks = 0
    try:
        from .security import locks
        d = locks() or {}
        security_locks = len(d.get("locks") or [])
    except Exception: pass
    kernel_status = "kernel artifact present, dormant, local-only"

    spoken = (
        "Colonel observation briefing. "
        f"The tower has {active_workers} active worker(s). "
        f"{len(active_floors)} floor(s) are currently active. "
        f"There are {open_practice} open OANDA practice trade(s). "
        + (f"The practice account balance is {account_balance} pounds. "
            if account_balance else "Practice account balance unavailable. ")
        + f"There are {pending_approvals} pending manager approval(s). "
        f"There are {not_working_warn} item(s) flagged as not working. "
        f"The {correction_pass}. "
        f"Security locks tracked: {security_locks}. "
        f"{kernel_status}. "
        "Real-money trading is off. Real OpenClaw execution is off. "
        "I am the Colonel and I am watching."
    )
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "COLONEL_AUDIO_BRIEFING",
        "active_workers": active_workers,
        "active_floor_count": len(active_floors),
        "top_alerts": top_alerts,
        "open_practice_trades": open_practice,
        "pending_approvals": pending_approvals,
        "not_working_warnings": not_working_warn,
        "correction_loop_summary": correction_pass,
        "spoken_text": spoken,
        "method": "browser_web_speech_synthesis",
        "execution_allowed": False,
    })


def speak(payload=None):
    return briefing()
