"""TowerGarden — ASCII rendering of the live tower for pure play. Reads
current registries and draws floors, lift cars, OpenClaw, density. Runs in
under 50 ms.

Why this exists: I wanted *one* thing that isn't useful, just nice. The
garden is for me. Sometimes I'll just render it before starting work.
"""
from __future__ import annotations
import json
import os
import random
from typing import Dict, List, Optional

ROOT = "/vaults/nvme0/qsb_tower_v1"

FLOOR_NAMES = {
    55: "Penthouse / Kernel",
    54: "Roof / Ops",
    53: "Tower Command",
    50: "ML/RL Lab",
    49: "DeepSeek Embassy",
    48: "GPT Embassy",
    47: "Claude Embassy",
    46: "Commerce Wing",
    44: "Accounts / PnL",
    43: "Stocks (paper)",
    42: "Binance (testnet)",
    41: "OANDA Trading",
    37: "Strategy Labs",
    35: "Hardware",
    31: "Audit / Ledger",
    30: "Guardian / Risk",
    28: "Security / Secrets",
    23: "AirLLM Chamber",
    22: "Lifts Dept",
    14: "Print-on-Demand",
    8:  "Training Academy",
    6:  "Etsy Shop Floor",
    1:  "Lobby",
}


def _read(rel: str) -> Optional[Dict]:
    p = os.path.join(ROOT, rel.lstrip("/"))
    if not os.path.exists(p): return None
    try:
        return json.load(open(p))
    except Exception:
        return None


def render(width: int = 78) -> str:
    master   = _read("data/registries/qsb_floor_interior_master_registry.json") or {"floors": []}
    lifts    = _read("data/registries/qsb_tower_lift_positions.json") or {"lifts": []}
    activity = _read("data/registries/qsb_floor_activity_stream_latest.json") or {}
    density  = _read("data/registries/qsb_tower_worker_density_map.json") or {}

    floors_by_id = {f["floor_id"]: f for f in master.get("floors", [])}
    lift_at_floor: Dict[int, List[int]] = {}
    for L in lifts.get("lifts", []):
        lift_at_floor.setdefault(int(L["current_floor"]), []).append(int(L["lift_id"]))

    dmap = density.get("density", {})

    lines: List[str] = []
    lines.append("┌" + "─" * (width - 2) + "┐")
    title = "QSB TOWER — live ASCII garden (Claude floor F47)"
    lines.append("│ " + title.center(width - 4) + " │")
    lines.append("├" + "─" * (width - 2) + "┤")

    for fl in range(55, 0, -1):
        name = FLOOR_NAMES.get(fl, "")
        d = dmap.get(f"F{fl:02d}", "")
        cars = lift_at_floor.get(fl, [])
        car_marker = ("⬛" * len(cars)) if cars else "  "
        # floor identity
        flag = "★" if fl == 47 else ("☆" if fl in (48, 49) else " ")
        body = f" F{fl:02d} {flag} {name:<22} " + ("│" * 1)
        # density bar
        try:
            density_n = int(d) if d != "" else 12
        except (TypeError, ValueError):
            density_n = 12
        bar_len = max(0, min(int(density_n / 4), 14))
        bar = "▓" * bar_len + "·" * (14 - bar_len)
        # activity event (1 line)
        ev = ""
        per_floor = activity.get("per_floor", {})
        if f"F{fl:02d}" in per_floor:
            ev = per_floor[f"F{fl:02d}"].get("text", "")[:24]
        # assemble row inside the box
        row = f"│ {body[:36]:<36} {bar} {car_marker:<6} {ev:<{max(0, width - 67)}}│"
        lines.append(row[:width])

    lines.append("├" + "─" * (width - 2) + "┤")
    legend = "★ Claude  ☆ GPT/DeepSeek  ⬛ lift car  ▓ density"
    lines.append("│ " + legend.ljust(width - 4) + " │")
    if activity.get("headline"):
        h = "headline: " + str(activity["headline"])[:width - 14]
        lines.append("│ " + h.ljust(width - 4) + " │")
    lines.append("└" + "─" * (width - 2) + "┘")
    return "\n".join(lines)


# Bonus: a tiny haiku generator over the current state — pure play.
def haiku() -> str:
    activity = _read("data/registries/qsb_floor_activity_stream_latest.json") or {}
    lifts    = _read("data/registries/qsb_tower_lift_positions.json") or {"lifts": []}
    n_lifts = len(lifts.get("lifts", []))
    headline = (activity.get("headline") or "the tower hums quietly").split("·")[0].strip()[:30]
    rng = random.Random(headline)
    line2_options = [
        f"{n_lifts} lifts crossing floors",
        "amber lamp on the desk",
        "violet on the back wall",
        "kernel speaks in low tones",
    ]
    line3_options = [
        "no live trades tonight",
        "Claude proposes, you decide",
        "execution gates closed",
        "morning will refresh state",
    ]
    return "\n".join([headline, rng.choice(line2_options), rng.choice(line3_options)])
