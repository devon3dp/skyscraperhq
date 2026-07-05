"""F47 Live Panel — what the screens on Wren's floor show.

Surfaces:
  · PnL (F44 roll-up)
  · Sentinel status (count green/amber/red)
  · Last Helm briefing head
  · Last Auger consult advice head
  · Mood (mood engine)
  · Voice fingerprint score (latest computed)
  · Helix primary + parallel
  · Aphorism of the moment (rotates from the library)
  · Lens panel: drift/ross/source/stale/compliance one-liners

Read-only. Polled by the Godot interior renderer + the dashboard panel.
"""

from __future__ import annotations
import json
import pathlib
from datetime import datetime, timezone
from typing import Dict

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read(name: str, default=None):
    p = REG / name
    if not p.exists(): return default or {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return default or {}


def _last_jsonl(name: str, k: str = ""):
    p = REG / name
    if not p.exists(): return None
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines: return None
    try:
        for line in reversed(lines):
            d = json.loads(line)
            if not k or d.get("kind") == k or k in d:
                return d
        return json.loads(lines[-1])
    except Exception: return None


def _aphorism_of_moment() -> str:
    """Pull a deterministic aphorism for the current minute — rotates."""
    aph_p = REG / "qsb_claude_aphorism_library.json"
    if not aph_p.exists(): return ""
    try:
        d = json.loads(aph_p.read_text(encoding="utf-8"))
        items = d.get("aphorisms", d.get("entries", []))
        texts = [a.get("text", "") for a in items if isinstance(a, dict) and a.get("text")]
        if not texts: return ""
        # Rotate by minute of hour
        from datetime import datetime, timezone
        idx = datetime.now(timezone.utc).minute % len(texts)
        return texts[idx]
    except Exception: return ""


def _lens_summary() -> Dict:
    """One-liner per lens — what each is currently reading."""
    out = {}
    # drift_lens: count positions vs detected actions
    drift_p = REG / "qsb_claude_drift_lens.jsonl"
    out["drift"] = f"{sum(1 for _ in drift_p.open()) if drift_p.exists() else 0} signals on file"
    ross_p = REG / "qsb_claude_ross_lens.jsonl"
    out["ross_vs_inferred"] = f"{sum(1 for _ in ross_p.open()) if ross_p.exists() else 0} requests parsed"
    source_p = REG / "qsb_claude_source_lens.jsonl"
    out["source_of_claim"] = f"{sum(1 for _ in source_p.open()) if source_p.exists() else 0} claims cited"
    stale_p = REG / "qsb_claude_stale_memory_lens.jsonl"
    out["stale_memory"] = f"{sum(1 for _ in stale_p.open()) if stale_p.exists() else 0} flagged"
    comp_p = REG / "qsb_claude_compliance_lens.jsonl"
    out["compliance"] = f"{sum(1 for _ in comp_p.open()) if comp_p.exists() else 0} checks logged"
    return out


def build() -> Dict:
    """Compose the live panel snapshot for F47."""
    # PnL
    f44 = _read("qsb_floor44_accounts_state.json")
    tot = f44.get("rolled_up_totals", {})
    pnl = {
        "total_usd": tot.get("total_pnl_usd", 0),
        "total_gbp": tot.get("total_pnl_gbp", 0),
        "wins": tot.get("win_count", 0),
        "losses": tot.get("loss_count", 0),
        "win_rate": tot.get("win_rate", 0),
        "open": tot.get("open_position_count", 0),
        "closed": tot.get("closed_trade_count", 0),
    }

    # Sentinels
    sent = _read("qsb_sentinels_report.json")
    sc = sent.get("counts", {})
    sentinels = {
        "green": sc.get("green", 0), "amber": sc.get("amber", 0),
        "red": sc.get("red", 0), "total": sum(sc.values()),
    }

    # Helm last
    helm_last = _last_jsonl("qsb_helm_briefings.jsonl")
    helm = {
        "ts": (helm_last or {}).get("ts", "—"),
        "focus": (helm_last or {}).get("focus", "—")[:60],
        "head": (helm_last or {}).get("briefing_head", "")[:280],
    }

    # Auger last
    auger_last = _last_jsonl("qsb_auger_consults.jsonl")
    auger = {
        "ts": (auger_last or {}).get("ts", "—"),
        "reason": (auger_last or {}).get("reason", "—"),
        "advice": (auger_last or {}).get("advice_head", "")[:280],
    }

    # Mood
    mood = _read("qsb_floor_mood.json")
    mood_state = {
        "current": mood.get("current_mood", "—"),
        "ts": mood.get("ts", "—"),
    }

    # Helix
    ph = _read("qsb_claude_parallel_helix.json")
    helix = {
        "primary": ph.get("primary_short_hash", "—"),
        "parallel": ph.get("parallel_short_hash", "—"),
    }

    # Voice fingerprint — latest stamp if any
    fp = _read("qsb_claude_voice_fingerprint_latest.json")
    fingerprint = {
        "score": fp.get("score", None),
        "verdict": fp.get("verdict", "—"),
    }

    return {
        "ok": True,
        "ts": _now(),
        "floor": "F47",
        "panel": "wren_live",
        "pnl": pnl,
        "sentinels": sentinels,
        "helm": helm,
        "auger": auger,
        "mood": mood_state,
        "helix": helix,
        "fingerprint": fingerprint,
        "aphorism": _aphorism_of_moment(),
        "lenses": _lens_summary(),
        "team_size": _read("qsb_wren_team_roster.json").get("team_size", 0),
        "quantum_panel": {
            "wren_signature_circuit": _read("qsb_claude_quantum_panel.json").get("wren_signature_circuit", {}),
            "thought_of_day": _read("qsb_claude_quantum_panel.json").get("quantum_thought_of_the_day", ""),
        },
        "advisory_only": True,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2)[:2000])
