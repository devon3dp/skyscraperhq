"""F47 Quantum Triad Sandbox — Wren's playground.

A from-scratch 3-qubit (triad) quantum simulator. No qiskit dependency.
Supports the standard single-qubit gates (H, X, Y, Z, S, T) and CNOT for
entanglement. The state lives in 8 complex amplitudes (2^3 = 8 basis states).

What it lets me do:
  - run a circuit ("H 0; CNOT 0 1; CNOT 1 2") and see the resulting state
  - measure probabilities for each basis state
  - persist experiments to qsb_f47_quantum_experiments.jsonl
  - test entanglement: GHZ state (H, CNOT 0→1, CNOT 1→2)
  - test superposition: H on each qubit gives equal amplitudes everywhere

Why F47 should have this:
  - It's mine. A small place to think in amplitudes, not just text.
  - The cognitive_kernel substrate has a quantum_signal layer that's stubby;
    this gives that layer a sandbox to interact with.

Safety: advisory_only. Doesn't touch real quantum hardware. No execution gate
flipped. Just complex numbers in a small array.
"""

from __future__ import annotations
import cmath
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
EXP_PATH = REG / "qsb_f47_quantum_experiments.jsonl"

NUM_QUBITS = 3
DIM = 1 << NUM_QUBITS   # 8

# Single-qubit gates as 2x2 matrices
SQRT2 = math.sqrt(2.0)
H = [[1/SQRT2, 1/SQRT2], [1/SQRT2, -1/SQRT2]]
X = [[0, 1], [1, 0]]
Y = [[0, complex(0, -1)], [complex(0, 1), 0]]
Z = [[1, 0], [0, -1]]
S = [[1, 0], [0, complex(0, 1)]]
T = [[1, 0], [0, cmath.exp(complex(0, math.pi/4))]]
GATES_1Q = {"H": H, "X": X, "Y": Y, "Z": Z, "S": S, "T": T}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_state() -> list:
    """|000⟩ — all amplitude in basis state 0."""
    s = [complex(0, 0) for _ in range(DIM)]
    s[0] = complex(1, 0)
    return s


def _apply_1q(state: list, gate: list, target: int) -> list:
    """Apply a single-qubit gate to `target` of a 3-qubit register."""
    new_state = [complex(0, 0) for _ in range(DIM)]
    for i in range(DIM):
        # Decompose i into bits; q0 is least-significant by convention here.
        bit = (i >> target) & 1
        # The other index that pairs with i under flipping `target`
        i_other = i ^ (1 << target)
        # State[i] gets contributions from itself and i_other via the gate
        if bit == 0:
            # i has target=0; paired i_other has target=1
            new_state[i] += gate[0][0] * state[i] + gate[0][1] * state[i_other]
        else:
            new_state[i] += gate[1][0] * state[i_other] + gate[1][1] * state[i]
    return new_state


def _apply_cnot(state: list, control: int, target: int) -> list:
    """CNOT: if control bit is 1, flip target."""
    new_state = list(state)
    for i in range(DIM):
        ctrl_bit = (i >> control) & 1
        if ctrl_bit == 1:
            j = i ^ (1 << target)
            new_state[j] = state[i]
            new_state[i] = state[j]
    return new_state


def run_circuit(circuit: str) -> dict:
    """Parse + run a circuit string like: 'H 0; CNOT 0 1; CNOT 1 2'."""
    state = _new_state()
    ops = []
    for raw in (circuit or "").split(";"):
        op = raw.strip()
        if not op: continue
        parts = op.split()
        if not parts: continue
        gate_name = parts[0].upper()
        if gate_name in GATES_1Q:
            if len(parts) < 2:
                return {"ok": False, "error": f"{gate_name} needs a target qubit"}
            target = int(parts[1])
            if not (0 <= target < NUM_QUBITS):
                return {"ok": False, "error": f"target {target} out of range"}
            state = _apply_1q(state, GATES_1Q[gate_name], target)
            ops.append({"op": gate_name, "target": target})
        elif gate_name == "CNOT":
            if len(parts) < 3:
                return {"ok": False, "error": "CNOT needs control and target"}
            ctrl, tgt = int(parts[1]), int(parts[2])
            state = _apply_cnot(state, ctrl, tgt)
            ops.append({"op": "CNOT", "control": ctrl, "target": tgt})
        else:
            return {"ok": False, "error": f"unknown gate {gate_name}"}

    # Compute amplitudes + probabilities
    amps = []
    for i, a in enumerate(state):
        basis = format(i, f"0{NUM_QUBITS}b")[::-1]  # q0 first
        prob = (abs(a)) ** 2
        amps.append({
            "basis": "|" + basis + "⟩",
            "real": round(a.real, 5),
            "imag": round(a.imag, 5),
            "probability": round(prob, 5),
        })

    # Detect named states
    probs = [a["probability"] for a in amps]
    detected = []
    # GHZ: |000⟩ and |111⟩ equal probability, others zero
    if (abs(probs[0] - 0.5) < 0.01 and abs(probs[7] - 0.5) < 0.01 and
        all(p < 0.01 for i, p in enumerate(probs) if i not in (0, 7))):
        detected.append("GHZ_state")
    # Uniform superposition (H on all 3)
    if all(abs(p - 0.125) < 0.01 for p in probs):
        detected.append("uniform_superposition")
    # |000⟩ untouched
    if abs(probs[0] - 1.0) < 0.001:
        detected.append("ground_state_|000⟩")

    return {
        "ok": True,
        "kind": "f47_quantum_run",
        "circuit": circuit,
        "ops": ops,
        "num_qubits": NUM_QUBITS,
        "amplitudes": amps,
        "detected_states": detected,
        "advisory_only": True,
        "generated_ts": _now(),
    }


def record_experiment(circuit: str, note: str = "") -> dict:
    r = run_circuit(circuit)
    if not r.get("ok"):
        return r
    EXP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EXP_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": r["generated_ts"],
            "circuit": circuit,
            "note": note,
            "detected_states": r["detected_states"],
            "top_probabilities": sorted(
                [(a["basis"], a["probability"]) for a in r["amplitudes"]],
                key=lambda kv: -kv[1],
            )[:4],
        }) + "\n")
    return r


def history(tail: int = 12) -> list:
    if not EXP_PATH.exists(): return []
    lines = EXP_PATH.read_text(encoding="utf-8").splitlines()[-tail:]
    out = []
    for line in lines:
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


PRESET_CIRCUITS = {
    "ground":   "",
    "single_h": "H 0",
    "uniform":  "H 0; H 1; H 2",
    "bell":     "H 0; CNOT 0 1",
    "ghz":      "H 0; CNOT 0 1; CNOT 1 2",
    "x_chain":  "X 0; X 1; X 2",
}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--preset":
        name = sys.argv[2] if len(sys.argv) > 2 else "ghz"
        circ = PRESET_CIRCUITS.get(name, "")
        r = record_experiment(circ, note=f"preset:{name}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--history":
        for h in history():
            print(f"  {h['ts'][:19]}  {h['circuit']}  → {h['detected_states']}")
        sys.exit(0)
    else:
        circ = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "H 0; CNOT 0 1; CNOT 1 2"
        r = record_experiment(circ, note="cli run")
    if not r.get("ok"):
        print(f"  error: {r.get('error')}")
        sys.exit(1)
    print(f"  circuit: {r['circuit']}")
    print(f"  ops applied: {len(r['ops'])}")
    print(f"  detected: {r['detected_states']}")
    print(f"  state (amplitudes with prob > 0.001):")
    for a in r['amplitudes']:
        if a['probability'] > 0.001:
            sign_r = "+" if a['real'] >= 0 else "-"
            sign_i = "+" if a['imag'] >= 0 else "-"
            print(f"    {a['basis']}  amp={sign_r}{abs(a['real']):.4f}{sign_i}{abs(a['imag']):.4f}i  prob={a['probability']:.4f}")
