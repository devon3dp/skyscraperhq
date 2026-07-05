"""src/workers/character.py — worker character + emotional state system.

Each worker gets a deterministic-from-hash trait vector + a dynamic mood
state. Hand-tuned anchors (Iris, Wren, Helm, Auger, Olga, Otto, Dex, plus
floor heads) override the procedural defaults via character_anchors.

Storage: traits live on the worker's floor_card.json under a `character`
key. Fast-changing mood / energy / last_events live in the bus SQLite
table `workers` (when the bus is built; for now a JSONL fallback at
data/registries/qsb_worker_mood.jsonl).

Read by:
- Dashboard / cockpit ("how's Floor 12 feeling?")
- Dating site / coworker pairing
- F47 chat narration (tone-matched replies)
- Wren when briefing Ross
"""
from __future__ import annotations
import hashlib, json, pathlib, time
from dataclasses import dataclass, field, asdict
from typing import Optional

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
MOOD_LOG = ROOT / "data/registries/qsb_worker_mood.jsonl"

# 0–9 axes
TRAIT_AXES = ("warm", "fast", "analytical", "creative", "risk")

# mood vocabulary — small + opinionated
MOOD_WORDS = (
    "steady", "lit up", "wound up", "burned out", "curious",
    "patient", "restless", "settled", "hungry", "wary",
    "glad", "cooled off", "wired", "easy", "quiet",
)


@dataclass
class Character:
    worker_id: str
    name: str
    role: str
    floor_id: int
    traits: dict[str, int] = field(default_factory=dict)
    voice: str = ""
    core_values: list[str] = field(default_factory=list)
    mood: str = "steady"
    energy: int = 5
    last_events: list[str] = field(default_factory=list)
    relationships: dict[str, dict] = field(default_factory=dict)
    is_anchor: bool = False
    last_drift_ts: Optional[str] = None


def procedural_traits(worker_id: str) -> dict[str, int]:
    """Deterministic 5-axis trait vector from worker_id hash. Same worker_id
    always gives the same vector — important for reproducibility."""
    h = hashlib.sha256(worker_id.encode()).digest()
    return {axis: h[i] % 10 for i, axis in enumerate(TRAIT_AXES)}


def procedural_voice(worker_id: str, role: str = "") -> str:
    """Procedurally generate a 1-line voice description from traits."""
    t = procedural_traits(worker_id)
    pieces = []
    if t["warm"] >= 7: pieces.append("warm")
    elif t["warm"] <= 2: pieces.append("clipped")
    if t["fast"] >= 7: pieces.append("quick")
    elif t["fast"] <= 2: pieces.append("deliberate")
    if t["analytical"] >= 7: pieces.append("precise")
    if t["creative"] >= 7: pieces.append("inventive")
    if t["risk"] >= 7: pieces.append("bold")
    elif t["risk"] <= 2: pieces.append("careful")
    voice = ", ".join(pieces) if pieces else "even-keeled"
    return f"{voice} {role}".strip()


def build_procedural_character(worker_id: str, name: str, role: str, floor_id: int) -> Character:
    return Character(
        worker_id=worker_id,
        name=name,
        role=role,
        floor_id=floor_id,
        traits=procedural_traits(worker_id),
        voice=procedural_voice(worker_id, role),
        core_values=[],
        mood="steady",
        energy=5,
        last_events=[],
        relationships={},
        is_anchor=False,
    )


def load_character(worker_id: str) -> Optional[Character]:
    """Load from anchor registry first, fall back to procedural."""
    try:
        from . import character_anchors
        anchor = character_anchors.get(worker_id)
        if anchor: return anchor
    except Exception:
        pass
    return None


# ── mood drift (cheap, bookkeeping only) ───────────────────────────────

def drift_mood(c: Character, floor_recent_kinds: list[str]) -> Character:
    """Nudge mood + energy based on what happened on the floor since last tick.

    Pure bookkeeping — NOT agentic. No model calls.

    Rules:
    - >=3 'tick' or '_ok' events → energy +1, mood may shift toward 'lit up'
    - any 'error' / 'failed' / 'crash' event → mood may shift to 'wound up'
    - no events at all → energy -1 (idle decay), mood may shift to 'quiet'
    - high warm + recent_events involve relationships → 'glad'
    - high analytical + recent_events involve audits → 'curious'
    """
    n_pos = sum(1 for k in floor_recent_kinds if any(s in k for s in ("tick","ok","passed","applied")))
    n_neg = sum(1 for k in floor_recent_kinds if any(s in k for s in ("error","failed","crash","reject")))
    if not floor_recent_kinds:
        c.energy = max(0, c.energy - 1)
        if c.energy <= 2: c.mood = "quiet"
    else:
        if n_pos >= 3:
            c.energy = min(9, c.energy + 1)
            if c.traits.get("warm",5) >= 6: c.mood = "lit up"
            elif c.traits.get("analytical",5) >= 6: c.mood = "curious"
            else: c.mood = "steady"
        if n_neg >= 1:
            c.mood = "wound up" if c.traits.get("warm",5) < 5 else "wary"
            if n_neg >= 3: c.mood = "burned out"
    c.last_drift_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return c


def stamp_mood(c: Character):
    """Append mood snapshot to the mood log jsonl."""
    MOOD_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": c.last_drift_ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "worker_id": c.worker_id,
        "name": c.name,
        "mood": c.mood,
        "energy": c.energy,
    }
    with MOOD_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


# ── compatibility (for the dating site / coworker pairing) ─────────────

def compatibility(a: Character, b: Character) -> float:
    """Heuristic 0..1 compatibility score.

    - Complementary on warm/fast/analytical (different is good for teams)
    - Aligned on risk and creative (same wavelength)
    - Bonus for prior warm relationship history
    """
    if a.worker_id == b.worker_id: return 0.0
    t1, t2 = a.traits, b.traits
    if not t1 or not t2: return 0.5
    complement = sum(abs(t1[ax] - t2[ax]) for ax in ("warm","fast","analytical")) / 30.0
    align = 1.0 - (sum(abs(t1[ax] - t2[ax]) for ax in ("risk","creative")) / 20.0)
    base = 0.5 * complement + 0.5 * align
    rel = a.relationships.get(b.worker_id, {})
    bonus = 0.1 if rel.get("sentiment") == "warm" else (-0.2 if rel.get("sentiment") == "cool" else 0)
    return max(0.0, min(1.0, base + bonus))
