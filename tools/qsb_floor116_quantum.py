#!/usr/bin/env python3
"""
qsb_floor116_quantum.py — Floor 116 "Quantum Lab" REAL job runner.

R01 HONESTY: this floor lights the Underground map ONLY from REAL quantum
simulation. There is NO fake QPU, NO cloud, NO decorative activity. Every job
is a genuine statevector computation done in numpy (100% real linear algebra),
run locally/offline. Measured outcomes are drawn from the true Born-rule
probabilities |amplitude|^2 of the simulated state.

The engine (class Statevector below) is a self-contained pure-numpy quantum
statevector simulator: H, X, Z, S, T, RY, CNOT, CZ, controlled-phase gates,
and Born-rule sampling. A few dozen lines of real quantum mechanics — no
external quantum library required, so the floor genuinely computes even fully
offline. (qiskit is present on this host but Aer is not; we do not depend on it.)

Each real job appends one row to:
    data/registries/qsb_floor116_quantum_activity.jsonl
with schema: {ts, room, job, qubits, real_result, worker, ...}.

The floor's 5 real assigned workers (from floors/floor_116_quantum_lab/floor_card.json)
run jobs in the floor's 5 real rooms. The freshness of this JSONL is what the
activity index (tools/qsb_floor_activity_index.py) detects to mark F116 active,
which lights F116 + emits its train on the Underground map (:8875).

Run one round of jobs:
    python3 tools/qsb_floor116_quantum.py

Self-verify the engine against known-exact results (no writes):
    python3 tools/qsb_floor116_quantum.py --selftest
"""
import json
import os
import sys
import time
import math
import random
import hashlib

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(REPO, "data", "registries")
OUT = os.path.join(REG, "qsb_floor116_quantum_activity.jsonl")
CARD = os.path.join(REPO, "floors", "floor_116_quantum_lab", "floor_card.json")

ISO = "%Y-%m-%dT%H:%M:%SZ"


def iso(ts=None):
    return time.strftime(ISO, time.gmtime(ts if ts is not None else time.time()))


# --------------------------------------------------------------------------
# REAL quantum statevector simulator (pure numpy — genuine linear algebra).
# Qubit ordering: qubit 0 is the most-significant bit of the basis-state index,
# so basis index b's bitstring is format(b, '0{n}b') with qubit i = that string[i].
# --------------------------------------------------------------------------
class Statevector:
    def __init__(self, n):
        self.n = n
        self.state = np.zeros(2 ** n, dtype=complex)
        self.state[0] = 1.0  # |00..0>

    def _apply_1q(self, U, q):
        """Apply a 2x2 unitary U to qubit q by reshaping the state tensor."""
        st = self.state.reshape([2] * self.n)
        st = np.moveaxis(st, q, 0)
        shape = st.shape
        st = st.reshape(2, -1)
        st = U @ st
        st = st.reshape(shape)
        st = np.moveaxis(st, 0, q)
        self.state = st.reshape(-1)

    # --- single-qubit gates ---
    def h(self, q):
        self._apply_1q(np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2), q)

    def x(self, q):
        self._apply_1q(np.array([[0, 1], [1, 0]], dtype=complex), q)

    def z(self, q):
        self._apply_1q(np.array([[1, 0], [0, -1]], dtype=complex), q)

    def s(self, q):
        self._apply_1q(np.array([[1, 0], [0, 1j]], dtype=complex), q)

    def t(self, q):
        self._apply_1q(np.array([[1, 0], [0, np.exp(1j * math.pi / 4)]], dtype=complex), q)

    def ry(self, theta, q):
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        self._apply_1q(np.array([[c, -s], [s, c]], dtype=complex), q)

    def phase(self, lam, q):
        self._apply_1q(np.array([[1, 0], [0, np.exp(1j * lam)]], dtype=complex), q)

    # --- controlled gates (built by masking basis states) ---
    def _controlled_apply(self, controls, U2, target):
        """Apply 2x2 U2 to `target` only on basis states where all `controls` are |1>."""
        n = self.n
        dim = 2 ** n
        new = self.state.copy()
        tbit = n - 1 - target
        cmask = 0
        for c in controls:
            cmask |= (1 << (n - 1 - c))
        done = np.zeros(dim, dtype=bool)
        for b in range(dim):
            if done[b]:
                continue
            if (b >> tbit) & 1:
                continue  # only handle target=0 partner, pair with target=1
            partner = b | (1 << tbit)
            done[b] = done[partner] = True
            if (b & cmask) != cmask:
                continue  # controls not all satisfied -> identity
            a0, a1 = self.state[b], self.state[partner]
            new[b] = U2[0, 0] * a0 + U2[0, 1] * a1
            new[partner] = U2[1, 0] * a0 + U2[1, 1] * a1
        self.state = new

    def cx(self, control, target):
        self._controlled_apply([control], np.array([[0, 1], [1, 0]], dtype=complex), target)

    def cz(self, control, target):
        self._controlled_apply([control], np.array([[1, 0], [0, -1]], dtype=complex), target)

    def ccz(self, c1, c2, target):
        self._controlled_apply([c1, c2], np.array([[1, 0], [0, -1]], dtype=complex), target)

    def cphase(self, lam, control, target):
        self._controlled_apply([control],
                               np.array([[1, 0], [0, np.exp(1j * lam)]], dtype=complex), target)

    # --- readout ---
    def probs(self):
        p = np.abs(self.state) ** 2
        return p / p.sum()

    def sample_counts(self, shots, rng):
        p = self.probs()
        idx = rng.choice(len(p), size=shots, p=p)
        counts = {}
        for b in idx:
            key = format(int(b), "0{}b".format(self.n))
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def entropy_bits(self):
        p = self.probs()
        nz = p[p > 1e-15]
        return float(-(nz * np.log2(nz)).sum())


# --------------------------------------------------------------------------
# REAL quantum jobs. Each returns a dict of genuine measured/computed results.
# --------------------------------------------------------------------------
def job_bell(rng, shots=2000):
    """2-qubit Bell state (|00>+|11>)/sqrt2 — measured counts must be ~50/50."""
    sv = Statevector(2)
    sv.h(0)
    sv.cx(0, 1)
    counts = sv.sample_counts(shots, rng)
    total = sum(counts.values())
    p00 = counts.get("00", 0) / total
    p11 = counts.get("11", 0) / total
    off = counts.get("01", 0) + counts.get("10", 0)
    return {
        "circuit": "H(q0); CNOT(q0,q1)",
        "shots": shots,
        "counts": counts,
        "p00": round(p00, 4),
        "p11": round(p11, 4),
        "off_diagonal_counts": off,   # must be 0 for a perfect Bell state
        "entanglement_entropy_bits": round(sv.entropy_bits(), 4),
        "note": "maximally-entangled: only |00> and |11> occur, ~50/50",
    }


def job_grover3(rng, marked=5, shots=2000):
    """3-qubit Grover search for a marked item (default |101>=5).
    Real amplitude amplification — the marked basis state dominates the counts."""
    n = 3
    sv = Statevector(n)
    for q in range(n):
        sv.h(q)
    mbits = format(marked, "0{}b".format(n))

    def oracle():
        # phase-flip |marked>: X-mask, CCZ, X-unmask
        for i, bit in enumerate(mbits):
            if bit == "0":
                sv.x(i)
        sv.ccz(0, 1, 2)
        for i, bit in enumerate(mbits):
            if bit == "0":
                sv.x(i)

    def diffuser():
        for q in range(n):
            sv.h(q)
            sv.x(q)
        sv.ccz(0, 1, 2)
        for q in range(n):
            sv.x(q)
            sv.h(q)

    iters = round(math.pi / 4 * math.sqrt(2 ** n))  # optimal ~2 for n=3
    for _ in range(iters):
        oracle()
        diffuser()
    counts = sv.sample_counts(shots, rng)
    top = next(iter(counts))
    p_marked = counts.get(mbits, 0) / sum(counts.values())
    return {
        "circuit": "3-qubit Grover, {} iterations".format(iters),
        "marked_item": "|{}> (={})".format(mbits, marked),
        "shots": shots,
        "counts": counts,
        "top_measured": "|{}>".format(top),
        "p_marked": round(p_marked, 4),
        "found": top == mbits,
        "note": "amplitude amplification concentrates probability on the marked item",
    }


def job_qft3(rng, shots=2000):
    """3-qubit Quantum Fourier Transform applied to |000>.
    QFT(|000>) = uniform superposition -> all 8 outcomes ~equal (entropy ~3 bits)."""
    n = 3
    sv = Statevector(n)

    def qft(sv, n):
        for j in range(n):
            sv.h(j)
            for k in range(j + 1, n):
                sv.cphase(math.pi / (2 ** (k - j)), k, j)
        # bit-reversal swaps
        for i in range(n // 2):
            # swap qubit i and n-1-i via 3 CNOTs
            a, b = i, n - 1 - i
            sv.cx(a, b)
            sv.cx(b, a)
            sv.cx(a, b)

    qft(sv, n)
    counts = sv.sample_counts(shots, rng)
    return {
        "circuit": "3-qubit QFT on |000>",
        "shots": shots,
        "counts": counts,
        "distinct_outcomes": len(counts),
        "entropy_bits": round(sv.entropy_bits(), 4),
        "note": "QFT of |000> is a uniform superposition: all 8 states ~equal, entropy~3.0",
    }


def job_qrng(rng, bits=8):
    """Quantum random-number generator: put `bits` qubits in H|0> and measure once.
    Each bit is a true 50/50 Born-rule draw from |+> = (|0>+|1>)/sqrt2."""
    sv = Statevector(bits)
    for q in range(bits):
        sv.h(q)
    # one shot = one genuine measurement of the uniform superposition
    p = sv.probs()
    outcome = int(rng.choice(len(p), p=p))
    bitstring = format(outcome, "0{}b".format(bits))
    return {
        "circuit": "{}x H|0> measured once".format(bits),
        "bits": bits,
        "draw_bitstring": bitstring,
        "draw_int": outcome,
        "draw_hex": "0x{:0{}x}".format(outcome, (bits + 3) // 4),
        "per_qubit_prob_one": 0.5,
        "note": "each qubit is a true Born-rule 50/50 quantum coin (uniform over 2^bits)",
    }


# --------------------------------------------------------------------------
# Job schedule: map real F116 rooms + real assigned workers to real jobs.
# --------------------------------------------------------------------------
def load_workers():
    try:
        card = json.load(open(CARD))
        ids = [w.get("id") for w in card.get("team_roster", []) if w.get("id")]
        if ids:
            return ids
    except Exception:
        pass
    return ["f116.floor_manager.01", "f116.operator.01", "f116.operator.02",
            "f116.operator.03", "f116.operator.04"]


def run_round(rng):
    workers = load_workers()
    fm = workers[0]
    ops = workers[1:] + [fm]
    schedule = [
        ("quantum_computing_hub",       "bell_state",    2, ops[0 % len(ops)], job_bell),
        ("algorithm_development_room",  "grover3",       3, ops[1 % len(ops)], job_grover3),
        ("quantum_simulation_room",     "qft3",          3, ops[2 % len(ops)], job_qft3),
        ("quantum_networking_room",     "quantum_rng",   8, ops[3 % len(ops)], job_qrng),
    ]
    rows = []
    for room, job_name, qubits, worker, fn in schedule:
        t0 = time.perf_counter()
        result = fn(rng)
        dt_ms = round((time.perf_counter() - t0) * 1000, 3)
        rows.append({
            "ts": iso(),
            "floor": 116,
            "room": room,
            "job": job_name,
            "qubits": qubits,
            "worker": worker,
            "real_result": result,
            "compute_ms": dt_ms,
            "engine": "qsb_numpy_statevector_v1",
            "honesty": "R01: real numpy statevector simulation, local/offline, no QPU/cloud",
        })
    return rows


def selftest():
    """Verify the engine against exact quantum-mechanical predictions. No writes."""
    rng = np.random.default_rng(12345)
    ok = True

    # Bell: off-diagonal must be exactly zero, entropy exactly 1 bit.
    b = job_bell(rng, shots=4000)
    cond = (b["off_diagonal_counts"] == 0 and abs(b["entanglement_entropy_bits"] - 1.0) < 1e-9)
    print("Bell     : p00={} p11={} off={} S={} -> {}".format(
        b["p00"], b["p11"], b["off_diagonal_counts"], b["entanglement_entropy_bits"],
        "PASS" if cond else "FAIL"))
    ok &= cond

    # Grover: marked item must be found and dominate (>0.9 for n=3, 2 iters).
    g = job_grover3(rng, marked=5, shots=4000)
    cond = g["found"] and g["p_marked"] > 0.9
    print("Grover3  : top={} p_marked={} found={} -> {}".format(
        g["top_measured"], g["p_marked"], g["found"], "PASS" if cond else "FAIL"))
    ok &= cond

    # QFT of |000> -> uniform, entropy must be exactly 3 bits, 8 distinct outcomes.
    q = job_qft3(rng, shots=8000)
    cond = (abs(q["entropy_bits"] - 3.0) < 1e-9 and q["distinct_outcomes"] == 8)
    print("QFT3     : distinct={} entropy={} -> {}".format(
        q["distinct_outcomes"], q["entropy_bits"], "PASS" if cond else "FAIL"))
    ok &= cond

    # QRNG: statistical check that each qubit is ~50/50 over many draws.
    ones = np.zeros(8)
    N = 5000
    for _ in range(N):
        r = job_qrng(rng, bits=8)
        for i, ch in enumerate(r["draw_bitstring"]):
            ones[i] += int(ch)
    fracs = ones / N
    cond = bool(np.all(np.abs(fracs - 0.5) < 0.05))
    print("QRNG     : per-qubit P(1)={} -> {}".format(
        [round(x, 3) for x in fracs], "PASS" if cond else "FAIL"))
    ok &= cond

    print("SELFTEST:", "ALL PASS" if ok else "FAILURE")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    # Real entropy source for the RNG seed (jobs are genuinely non-deterministic run-to-run).
    seed = int.from_bytes(os.urandom(8), "big")
    rng = np.random.default_rng(seed)
    rows = run_round(rng)
    os.makedirs(REG, exist_ok=True)
    with open(OUT, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    for r in rows:
        rr = r["real_result"]
        head = rr.get("top_measured") or rr.get("draw_bitstring") or \
            "S={}".format(rr.get("entanglement_entropy_bits") or rr.get("entropy_bits"))
        print("[F116 {:<28}] {:<12} q={} worker={} -> {}".format(
            r["room"], r["job"], r["qubits"], r["worker"], head))
    print("wrote {} real quantum job rows -> {}".format(len(rows), os.path.relpath(OUT, REPO)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
