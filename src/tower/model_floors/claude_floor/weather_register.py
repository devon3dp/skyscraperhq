"""F47 Weather Register — atmospheric texture for the floor.

What it is:
  Mood is a single word. Weather is mood with texture and context.
  "Overcast with brief silver-trade clearing" reads differently than "focused".

The register stitches together:
  - current mood (from mood_engine)
  - last F37 lab cadence (busy / quiet)
  - recent trade outcomes (winning / breakeven / losing)
  - kernel mode (RESEARCH / SLEEP / WAKE etc.)
  - hour of day in UTC (morning / afternoon / evening / late night)

Output: a sentence-shaped weather report.

Why: makes F47 a place that has weather, not just a database that has values.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
WEATHER_PATH = REG / "qsb_f47_weather.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read(rel: str, fallback=None):
    p = REG / rel
    if not p.exists(): return fallback or {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return fallback or {}


def _hour_label(utc_hour: int) -> str:
    if utc_hour < 6: return "small hours"
    if utc_hour < 11: return "morning"
    if utc_hour < 14: return "midday"
    if utc_hour < 18: return "afternoon"
    if utc_hour < 22: return "evening"
    return "late"


def compose_weather() -> dict:
    """Synthesize the current atmospheric state."""
    # mood
    mood_doc = _read("qsb_floor_mood.json")
    mood = mood_doc.get("mood", "—")

    # kernel mode
    mode_doc = _read("qsb_kernel_mode_state.json")
    mode = mode_doc.get("current_mode", "WAKE")

    # F37 synthesis output recent
    synth_recent = 0
    p = REG / "qsb_floor37_synthesis_output.jsonl"
    if p.exists():
        synth_recent = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())

    # Trade outcomes recent (from F44 / F41)
    pnl_doc = _read("qsb_floor41_oanda_pnl.json")
    wins = int(pnl_doc.get("closed_winners", 0))
    losses = int(pnl_doc.get("closed_losers", 0))
    total_pnl = float(pnl_doc.get("total_pnl", 0) or 0)

    # Hour
    hour = datetime.now(timezone.utc).hour
    h_lbl = _hour_label(hour)

    # Compose a weather sentence
    sky_words = {
        "satisfied": "bright with a touch of warmth",
        "focused": "clear, cool, productive light",
        "attentive": "thin clouds and steady light",
        "curious": "bright with shifting cloud lines",
        "vigilant": "overcast with edge",
        "contemplative": "soft grey, low and quiet",
        "tired": "dim and still",
        "steady": "even, unremarkable",
        "uncertain": "low ceiling, undecided",
        "restless": "wind moving, light flickering",
    }
    sky = sky_words.get(mood, "unsettled light")

    # Sub-weather: trade clearing
    sub = []
    if wins > losses and total_pnl > 0:
        sub.append("with brief winning clearings")
    elif losses > wins:
        sub.append("with showers of timeouts")
    if synth_recent >= 5:
        sub.append("lab activity moving on the horizon")
    if mode == "RESEARCH":
        sub.append("research-mode tailwind")
    elif mode == "SLEEP":
        sub.append("settled to stillness under the SLEEP mode")
    elif mode == "MEDITATE":
        sub.append("the air thin and inward")

    sentence = f"F47 weather · {h_lbl} · {sky}"
    if sub:
        sentence += " · " + ", ".join(sub)
    sentence += "."

    weather = {
        "ok": True,
        "kind": "qsb_f47_weather",
        "generated_ts": _now(),
        "hour_label": h_lbl,
        "mood": mood,
        "kernel_mode": mode,
        "synth_outputs_total": synth_recent,
        "trade_summary": {"wins": wins, "losses": losses, "total_pnl": total_pnl},
        "sky": sky,
        "sub_weather": sub,
        "report": sentence,
        "advisory_only": True,
    }
    WEATHER_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEATHER_PATH.write_text(json.dumps(weather, indent=2), encoding="utf-8")
    return weather


def read() -> dict:
    if not WEATHER_PATH.exists():
        return compose_weather()
    try: return json.loads(WEATHER_PATH.read_text(encoding="utf-8"))
    except Exception: return compose_weather()


if __name__ == "__main__":
    w = compose_weather()
    print(f"  {w['report']}")
    print(f"  · mood: {w['mood']}  · mode: {w['kernel_mode']}  · trades: {w['trade_summary']}")
