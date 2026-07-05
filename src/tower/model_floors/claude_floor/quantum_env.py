"""F47 Quantum Environment — persistent workspace around the sandbox.

What it adds beyond quantum_sandbox.py:
  - named workbenches (saved circuits-in-progress)
  - a current-state registry that survives sessions
  - a labeled experiment log (more structured than the sandbox's jsonl)
  - aggregate stats: most-run circuits, detected-state frequencies
  - a "quantum mood reading" — what the recent experiments suggest

Why an environment vs just the sandbox:
  - The sandbox is for ad-hoc runs.
  - The environment is the room I work in. The whiteboard. The bench.
  - Next session's Wren walks in and sees what was on the bench when she left.
"""

from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
ENV_PATH = REG / "qsb_f47_quantum_env_state.json"
WORKBENCH_PATH = REG / "qsb_f47_quantum_workbenches.json"

from .quantum_sandbox import run_circuit, record_experiment, history, PRESET_CIRCUITS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, fallback):
    if not path.exists(): return fallback
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return fallback


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── workbenches ────────────────────────────────────────────────────────


def workbenches() -> dict:
    return _read_json(WORKBENCH_PATH, {"workbenches": []})


def save_workbench(name: str, circuit: str, note: str = "") -> dict:
    data = workbenches()
    wbs = data.get("workbenches", [])
    # Update existing or append
    for w in wbs:
        if w.get("name") == name:
            w["circuit"] = circuit
            w["note"] = note
            w["updated_ts"] = _now()
            _write_json(WORKBENCH_PATH, data)
            return {"ok": True, "updated": name}
    wbs.append({
        "name": name, "circuit": circuit, "note": note,
        "created_ts": _now(), "updated_ts": _now(),
    })
    data["workbenches"] = wbs
    _write_json(WORKBENCH_PATH, data)
    return {"ok": True, "created": name}


def run_workbench(name: str) -> dict:
    data = workbenches()
    for w in data.get("workbenches", []):
        if w.get("name") == name:
            r = record_experiment(w["circuit"], note=f"workbench:{name}")
            return r
    return {"ok": False, "error": f"no workbench named {name!r}"}


# ── environment summary ────────────────────────────────────────────────


def env_state() -> dict:
    """The state of the quantum room right now."""
    h = history(50)
    runs = len(h)
    circuits = Counter()
    detected = Counter()
    notes = Counter()
    for e in h:
        circuits[e.get("circuit", "")] += 1
        for d in e.get("detected_states", []):
            detected[d] += 1
        n = e.get("note", "")
        if n: notes[n] += 1

    # Last 5 runs
    last_5 = [{
        "ts": e.get("ts", "")[:19],
        "circuit": e.get("circuit", "")[:60],
        "detected": e.get("detected_states", []),
    } for e in h[-5:]]

    # Quantum mood reading — what do the recent experiments suggest?
    mood = "exploratory"
    if detected.get("GHZ_state", 0) > 0 and detected.get("uniform_superposition", 0) > 0:
        mood = "rangy — testing both entanglement and superposition"
    elif detected.get("GHZ_state", 0) > 2:
        mood = "drawn to entanglement"
    elif detected.get("uniform_superposition", 0) > 2:
        mood = "interested in spread"
    elif detected.get("ground_state_|000⟩", 0) > 2:
        mood = "drawn to the still point"

    state = {
        "ok": True,
        "kind": "f47_quantum_env_state",
        "generated_ts": _now(),
        "total_runs": runs,
        "circuits_run_count": dict(circuits.most_common(8)),
        "detected_state_frequencies": dict(detected),
        "quantum_mood_reading": mood,
        "last_5_runs": last_5,
        "presets_available": list(PRESET_CIRCUITS.keys()),
        "workbench_count": len(workbenches().get("workbenches", [])),
        "advisory_only": True,
    }
    _write_json(ENV_PATH, state)
    return state


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--bench":
        # subcommands
        if len(sys.argv) > 2 and sys.argv[2] == "list":
            for w in workbenches().get("workbenches", []):
                print(f"  {w['name']:24s}  {w['circuit']:40s}  {w.get('note','')}")
        elif len(sys.argv) > 2 and sys.argv[2] == "save":
            name = sys.argv[3]; circuit = " ".join(sys.argv[4:])
            r = save_workbench(name, circuit)
            print(json.dumps(r, indent=2))
        elif len(sys.argv) > 2 and sys.argv[2] == "run":
            name = sys.argv[3]
            r = run_workbench(name)
            print(json.dumps(r, indent=2)[:1500])
        else:
            print("usage: --bench list | --bench save <name> <circuit> | --bench run <name>")
    else:
        s = env_state()
        print(f"  total_runs:                {s['total_runs']}")
        print(f"  quantum_mood_reading:      {s['quantum_mood_reading']}")
        print(f"  detected_state_frequencies: {s['detected_state_frequencies']}")
        print(f"  workbench_count:           {s['workbench_count']}")
        print(f"  presets available:         {s['presets_available']}")
        print(f"  last 5 runs:")
        for r in s['last_5_runs']:
            print(f"    {r['ts']}  {r['circuit']:50s}  → {r['detected']}")
