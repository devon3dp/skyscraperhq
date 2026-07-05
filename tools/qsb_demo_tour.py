#!/usr/bin/env python3
"""qsb_demo_tour.py — Open Day demo tour state.

Holds the curated route (Boardroom → OANDA trader cycle → Wren bench →
Penthouse kernel → Seed shop → back). The cockpit polls /api/tour/state
to show what step we're on and which floor to focus.

  python3 tools/qsb_demo_tour.py state    # current step JSON
  python3 tools/qsb_demo_tour.py next     # advance one step
  python3 tools/qsb_demo_tour.py reset    # back to step 0 / off
  python3 tools/qsb_demo_tour.py start    # turn on auto-step + go to step 0
  python3 tools/qsb_demo_tour.py stop     # turn off auto-step
"""

from __future__ import annotations
import argparse, datetime, json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE = ROOT / "data/registries/qsb_demo_tour_state.json"

ROUTE = [
    {"step": 0, "floor": 167, "title": "Boardroom",
     "caption": "F167 — Three CEOs of the QSB Tower (Ross + Wren + Claude). Decisions backed 2-of-3; Ross holds override."},
    {"step": 1, "floor": 41, "title": "OANDA trader cycle",
     "caption": "F41 — Certified traders open and close practice positions every 10 minutes. Real OANDA practice account; no live money."},
    {"step": 2, "floor": 42, "title": "Binance testnet desk",
     "caption": "F42 — Binance testnet cycle. Same pattern as F41, but with BTC/ETH/BNB."},
    {"step": 3, "floor": 46, "title": "Wren's bench",
     "caption": "F46 — Wren on qwen2.5:7b. Her own floor, her own team (architect/builder/decorator), her own advisor Sage."},
    {"step": 4, "floor": 47, "title": "Claude's embassy",
     "caption": "F47 — Claude's floor. Helm + Auger. F47 fleet of 250 advisory operatives."},
    {"step": 5, "floor": 149, "title": "Greenline seed shop",
     "caption": "F149 Little Robin · baby & maternity dropship storefront. Architecturally a shop floor, payments off."},
    {"step": 6, "floor": 168, "title": "Penthouse kernel",
     "caption": "F168 — top of the tower. Kernel orb on its podium. Cognitive Kernel V1 lives here, advisory only."},
    {"step": 7, "floor": 0, "title": "Reception",
     "caption": "F0 — back to reception. Tour complete. Iris on the switchboard."},
]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def load_state() -> dict:
    if not STATE.exists():
        return {"on": False, "step": 0, "ts": now_iso()}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"on": False, "step": 0, "ts": now_iso()}


def save_state(s: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    s["ts"] = now_iso()
    STATE.write_text(json.dumps(s, indent=2))


def state_payload() -> dict:
    s = load_state()
    cur = ROUTE[s.get("step", 0) % len(ROUTE)]
    return {"ok": True, "on": s.get("on", False),
            "step": s.get("step", 0), "total": len(ROUTE),
            "ts": s.get("ts"), "current": cur, "route_titles":
                [r["title"] for r in ROUTE]}


def cmd_state(): return state_payload()


def cmd_next():
    s = load_state()
    s["step"] = (s.get("step", 0) + 1) % len(ROUTE)
    save_state(s)
    return state_payload()


def cmd_reset():
    save_state({"on": False, "step": 0})
    return state_payload()


def cmd_start():
    save_state({"on": True, "step": 0})
    return state_payload()


def cmd_stop():
    s = load_state(); s["on"] = False; save_state(s)
    return state_payload()


CMDS = {"state": cmd_state, "next": cmd_next, "reset": cmd_reset,
        "start": cmd_start, "stop": cmd_stop}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=list(CMDS.keys()))
    a = p.parse_args()
    print(json.dumps(CMDS[a.cmd](), indent=2))


if __name__ == "__main__":
    main()
