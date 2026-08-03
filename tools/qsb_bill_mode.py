#!/usr/bin/env python3
"""
qsb_bill_mode.py — Bill's HIGH-LEVEL mode selector (work | concierge | both).

Ross 2026-07-29: "he has to have his work mode and concierge mode."

Bill is ONE mind on his Mac (qwen2.5:14b, outbound-only, polls relay :8855). ONE
mind, TWO modes. This module is the single source of truth for WHICH mode Bill is
in and it DRIVES the existing lease/quorum engine (qsb_bill_work_mode.py) so the
two stay consistent.

  WORK MODE      Bill claims + executes real council tasks through his tower tools
                 / the work-mode lease. counts_for_quorum can be TRUE. Non-self-
                 verifying (Wren's 2-CEO gene-pool quorum verifies). Routine 30-min
                 concierge status pushes are SUPPRESSED (quiet) — only URGENT alerts
                 still relay to Ross.
  CONCIERGE MODE Bill monitors the tower + relays to Ross. He does NOT claim council
                 tasks (counts_for_quorum FALSE / no work lease). Concierge pushes
                 ENABLED.
  BOTH           Bill does LIGHT work (rate-limited to work_cap_both in flight so
                 monitoring is never starved) AND concierges. Work lease active +
                 concierge pushes ENABLED.

COEXISTENCE (no conflict):
  * URGENT concierge alerts relay in ANY mode — work never mutes a real emergency.
  * In pure WORK mode, routine status pushes go quiet so Bill focuses.
  * In BOTH, work is capped (work_cap_both) so concierge monitoring isn't starved.

HOW ROSS SWITCHES IT:
  * CLI:   python3 tools/qsb_bill_mode.py --set work|concierge|both [--reason "..."]
  * RELAY: Ross messages Bill "go to work mode" / "concierge mode" / "both mode" on
           the leadership relay. Bill's responder (deploy/qsb_bill_responder.py)
           recognises the phrase and calls back to this module to set the mode, so
           the switch is a genuine round-trip through Bill's own real Mac mind.

DURABLE: mode persists in data/registries/qsb_bill_mode.json and survives restarts
(default after any restart is whatever was last set, falling back to 'concierge').

Non-destructive. Never fabricates work. When Bill's Mac mind is unreachable, work is
HONESTLY skipped — the mode machinery still reports correctly.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
STATE = os.path.join(ROOT, "data", "registries", "qsb_bill_mode.json")

import qsb_bill_work_mode as WM  # the lease/quorum engine this module drives

VALID_MODES = ("work", "concierge", "both")
# Phrases (lower-cased, punctuation-stripped) Ross can say to switch mode.
PHRASE_MAP = {
    "work": ("go to work mode", "work mode", "go work", "start work",
             "work mode on", "get to work", "back to work"),
    "concierge": ("concierge mode", "go to concierge mode", "go concierge",
                  "stand down", "concierge mode on", "just concierge",
                  "back to concierge"),
    "both": ("both mode", "go to both mode", "do both", "work and concierge",
             "both work and concierge", "both modes", "hybrid mode"),
}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _load() -> dict:
    with open(STATE) as f:
        return json.load(f)


def _save(s: dict) -> None:
    with open(STATE, "w") as f:
        json.dump(s, f, indent=2)


# ── mode read ────────────────────────────────────────────────────────────────

def get_mode() -> str:
    try:
        m = _load().get("mode", "concierge")
        return m if m in VALID_MODES else "concierge"
    except Exception:
        return "concierge"


def status() -> dict:
    """Full mode picture: high-level mode + the underlying lease/quorum status."""
    try:
        s = _load()
    except Exception:
        s = {"mode": "concierge"}
    wm = WM.status()
    mode = s.get("mode", "concierge")
    return {
        "mode": mode,
        "set_by": s.get("set_by"),
        "set_at": s.get("set_at"),
        "reason": s.get("reason"),
        "work_enabled": mode in ("work", "both"),
        "concierge_pushes_enabled": mode in ("concierge", "both"),
        "concierge_quiet_routine": mode == "work",  # routine muted, urgent still fires
        "counts_for_quorum": bool(wm.get("counts_for_quorum")),
        "work_lease": {
            "mode": wm.get("mode"),
            "enabled": wm.get("enabled"),
            "lease_expires_at": wm.get("lease_expires_at"),
            "heartbeat_age_seconds": wm.get("heartbeat_age_seconds"),
            "endpoint_probe_ok": wm.get("endpoint_probe_ok"),
        },
        "panel": WM.panel_state(),
    }


# ── gating helpers (imported by the worker + agent + responder) ──────────────

def work_allowed() -> bool:
    """True if the high-level mode permits Bill to CLAIM/EXECUTE council tasks."""
    return get_mode() in ("work", "both")


def concierge_push_allowed(urgent: bool = False) -> bool:
    """True if Bill may push a concierge status update to Ross right now.

    URGENT alerts are allowed in EVERY mode (work never mutes an emergency).
    Routine pushes are allowed in concierge/both; suppressed in pure work mode.
    """
    if urgent:
        return True
    return get_mode() in ("concierge", "both")


def work_cap() -> int:
    """Max in-flight council tasks Bill may hold, given the mode.
    'both' is deliberately capped low so concierge monitoring is never starved."""
    m = get_mode()
    if m == "concierge":
        return 0
    if m == "both":
        try:
            return int(_load().get("work_cap_both", 1))
        except Exception:
            return 1
    return int(os.environ.get("BILL_WORK_CAP", "2"))  # pure work mode


# ── mode set (drives the lease engine to stay consistent) ────────────────────

def set_mode(mode: str, set_by: str = "ross", reason: str = "",
             lease_seconds: int = 3600) -> dict:
    """Set Bill's high-level mode and reconcile the lease/quorum engine.

    work / both  -> enable a fresh work lease (Bill can count for quorum once his
                    mind heartbeats fresh with endpoint_probe_ok).
    concierge    -> disable the work lease (back to Executive Concierge default).

    This does NOT fake Bill's mind being live — it only sets intent + the lease.
    counts_for_quorum still requires a fresh heartbeat + endpoint probe, which only
    happens when Bill's real Mac responder answers (ensure_bill_work_mode / probe).
    """
    mode = (mode or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; must be one of {VALID_MODES}")
    s = _load()
    prev = s.get("mode")
    now = _now()
    s["mode"] = mode
    s["set_by"] = set_by
    s["set_at"] = _iso(now)
    s["reason"] = reason or f"set to {mode} by {set_by}"
    hist = s.get("history", [])
    hist.append({"ts": _iso(now), "from": prev, "to": mode,
                 "set_by": set_by, "reason": s["reason"]})
    s["history"] = hist[-50:]
    _save(s)

    # Reconcile the underlying lease engine.
    if mode in ("work", "both"):
        WM.enable(set_by, f"mode->{mode}: {s['reason']}", lease_seconds=lease_seconds)
    else:  # concierge
        WM.disable()

    return status()


# ── relay-phrase recognition (used by Bill's responder) ──────────────────────

def parse_mode_command(text: str):
    """Return a mode name if `text` is a mode-switch command, else None.

    Recognises Ross's natural phrasing ('go to work mode', 'concierge mode',
    'both mode', 'stand down', 'get to work', ...). Case/punctuation-insensitive.
    Longest, most-specific phrases win (so 'both work and concierge' -> both,
    not work). Bill's responder calls this on every inbound message.
    """
    if not text:
        return None
    low = "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower())
    low = " ".join(low.split())
    # score by longest matching phrase to avoid 'work mode' shadowing 'both ... work'
    best = (None, 0)
    for mode, phrases in PHRASE_MAP.items():
        for p in phrases:
            if p in low and len(p) > best[1]:
                best = (mode, len(p))
    return best[0]


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    ap = argparse.ArgumentParser(description="Bill's high-level mode selector (work|concierge|both).")
    ap.add_argument("--status", action="store_true", help="show full mode + lease status")
    ap.add_argument("--get", action="store_true", help="print just the current mode word")
    ap.add_argument("--set", metavar="MODE", choices=VALID_MODES, help="set mode: work|concierge|both")
    ap.add_argument("--by", default="ross", help="who is setting the mode (audit)")
    ap.add_argument("--reason", default="", help="reason (audit)")
    ap.add_argument("--lease", type=int, default=3600, help="work-lease seconds (work/both)")
    ap.add_argument("--parse", metavar="TEXT", help="test the relay-phrase parser on TEXT")
    ap.add_argument("--selftest", action="store_true", help="non-destructive machinery self-test")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if a.parse is not None:
        print(parse_mode_command(a.parse) or "(not a mode command)")
        return 0
    if a.get:
        print(get_mode())
        return 0
    if a.set:
        st = set_mode(a.set, set_by=a.by, reason=a.reason, lease_seconds=a.lease)
        print(json.dumps(st, indent=2))
        return 0
    # default: status
    print(json.dumps(status(), indent=2))
    return 0


def _selftest():
    """Prove the mode machinery non-destructively (snapshot + restore both files)."""
    import copy
    orig_mode = _load()
    orig_wm = WM._load()
    checks = []
    try:
        # 1. concierge gates work off, pushes on
        set_mode("concierge", "selftest", "st")
        checks.append(("concierge: work NOT allowed", work_allowed() is False))
        checks.append(("concierge: routine push allowed", concierge_push_allowed() is True))
        checks.append(("concierge: work_cap 0", work_cap() == 0))
        checks.append(("concierge: lease disabled", WM.status().get("enabled") is False))

        # 2. work gates work on, routine push off, urgent still on
        set_mode("work", "selftest", "st")
        checks.append(("work: work allowed", work_allowed() is True))
        checks.append(("work: routine push SUPPRESSED", concierge_push_allowed() is False))
        checks.append(("work: URGENT push still allowed", concierge_push_allowed(urgent=True) is True))
        checks.append(("work: lease enabled", WM.status().get("enabled") is True))

        # 3. both gates work on AND pushes on, capped
        set_mode("both", "selftest", "st")
        checks.append(("both: work allowed", work_allowed() is True))
        checks.append(("both: routine push allowed", concierge_push_allowed() is True))
        checks.append(("both: work capped low", work_cap() == int(_load().get("work_cap_both", 1))))
        checks.append(("both: lease enabled", WM.status().get("enabled") is True))

        # 4. persistence: mode written to disk survives a fresh read
        checks.append(("persist: get_mode reads 'both'", get_mode() == "both"))

        # 5. relay-phrase parser
        checks.append(("parse 'go to work mode' -> work", parse_mode_command("go to work mode") == "work"))
        checks.append(("parse 'concierge mode please' -> concierge", parse_mode_command("concierge mode please") == "concierge"))
        checks.append(("parse 'both mode' -> both", parse_mode_command("both mode") == "both"))
        checks.append(("parse 'do both work and concierge' -> both", parse_mode_command("do both work and concierge") == "both"))
        checks.append(("parse 'stand down' -> concierge", parse_mode_command("stand down") == "concierge"))
        checks.append(("parse 'hello bill' -> None", parse_mode_command("hello bill") is None))
        checks.append(("invalid mode rejected", _rejects_invalid()))

        allok = True
        for n, r in checks:
            print(f"  [{'PASS' if r else 'FAIL'}] {n}")
            allok = allok and r
        print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
        return 0 if allok else 1
    finally:
        _save(orig_mode)
        WM._save(orig_wm)


def _rejects_invalid():
    try:
        set_mode("banana")
        return False
    except ValueError:
        return True


if __name__ == "__main__":
    sys.exit(_cli())
