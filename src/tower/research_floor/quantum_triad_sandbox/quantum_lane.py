"""QuantumLane — pure-Python classical simulation of small quantum systems.

State vectors are lists of complex numbers, length 2**n.
Gates are 2x2 (or 4x4) complex matrices applied via tensor product expansion.
Measurement implements the Born rule with weighted sampling.

No numpy. Mathematics is the same; transparency is higher.
Capped at 4 qubits (state vector length 16).
"""
from __future__ import annotations
import cmath
import math
import random
from typing import Dict, List, Optional, Tuple

Complex = complex
Matrix = List[List[Complex]]
Vector = List[Complex]


# ── linear algebra primitives ────────────────────────────────────────────
def _matvec(M: Matrix, v: Vector) -> Vector:
    n = len(M)
    out: Vector = [Complex(0, 0)] * n
    for i in range(n):
        s = Complex(0, 0)
        row = M[i]
        for j in range(n):
            s += row[j] * v[j]
        out[i] = s
    return out


def _matmat(A: Matrix, B: Matrix) -> Matrix:
    n, m = len(A), len(B[0])
    inner = len(B)
    out: Matrix = [[Complex(0, 0)] * m for _ in range(n)]
    for i in range(n):
        for k in range(inner):
            a_ik = A[i][k]
            if a_ik == 0: continue
            for j in range(m):
                out[i][j] += a_ik * B[k][j]
    return out


def _kron(A: Matrix, B: Matrix) -> Matrix:
    rA, cA, rB, cB = len(A), len(A[0]), len(B), len(B[0])
    out: Matrix = [[Complex(0, 0)] * (cA * cB) for _ in range(rA * rB)]
    for i in range(rA):
        for j in range(cA):
            for p in range(rB):
                for q in range(cB):
                    out[i * rB + p][j * cB + q] = A[i][j] * B[p][q]
    return out


def _eye(n: int) -> Matrix:
    return [[Complex(1, 0) if i == j else Complex(0, 0) for j in range(n)] for i in range(n)]


# ── gates ────────────────────────────────────────────────────────────────
class Gates:
    I: Matrix = [[Complex(1, 0), Complex(0, 0)],
                  [Complex(0, 0), Complex(1, 0)]]
    X: Matrix = [[Complex(0, 0), Complex(1, 0)],
                  [Complex(1, 0), Complex(0, 0)]]
    Y: Matrix = [[Complex(0, 0), Complex(0, -1)],
                  [Complex(0, 1),  Complex(0, 0)]]
    Z: Matrix = [[Complex(1, 0),  Complex(0, 0)],
                  [Complex(0, 0),  Complex(-1, 0)]]
    H: Matrix = [
        [Complex(1 / math.sqrt(2), 0), Complex(1 / math.sqrt(2), 0)],
        [Complex(1 / math.sqrt(2), 0), Complex(-1 / math.sqrt(2), 0)],
    ]
    S: Matrix = [[Complex(1, 0), Complex(0, 0)], [Complex(0, 0), Complex(0, 1)]]
    T: Matrix = [[Complex(1, 0), Complex(0, 0)],
                  [Complex(0, 0), cmath.exp(Complex(0, math.pi / 4))]]

    @staticmethod
    def rx(theta: float) -> Matrix:
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return [[Complex(c, 0), Complex(0, -s)],
                [Complex(0, -s), Complex(c, 0)]]

    @staticmethod
    def ry(theta: float) -> Matrix:
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return [[Complex(c, 0), Complex(-s, 0)],
                [Complex(s, 0), Complex(c, 0)]]

    @staticmethod
    def rz(theta: float) -> Matrix:
        return [[cmath.exp(Complex(0, -theta / 2)), Complex(0, 0)],
                [Complex(0, 0), cmath.exp(Complex(0, theta / 2))]]


def _gate_name(U: Matrix) -> str:
    for n, g in (("X", Gates.X), ("Y", Gates.Y), ("Z", Gates.Z),
                 ("H", Gates.H), ("S", Gates.S), ("T", Gates.T)):
        eq = True
        for i in range(2):
            for j in range(2):
                if abs(U[i][j] - g[i][j]) > 1e-9:
                    eq = False; break
            if not eq: break
        if eq: return n
    return "U"


# ── lane ─────────────────────────────────────────────────────────────────
class QuantumLane:
    MAX_QUBITS = 8           # v13.14: pushed from 4 → 8 via sparse gates

    def __init__(self, n_qubits: int) -> None:
        if not 1 <= n_qubits <= self.MAX_QUBITS:
            raise ValueError(f"n_qubits must be 1..{self.MAX_QUBITS}")
        self.n = n_qubits
        self.state: Vector = [Complex(0, 0)] * (2 ** n_qubits)
        self.state[0] = Complex(1, 0)
        self.history: List[str] = []

    # v13.14: O(N) single-qubit application — no more full N×N kron product.
    # For qubit q, iterate basis states with bit-q=0 and update pairs (i, i|mask).
    def apply(self, U: Matrix, q: int) -> "QuantumLane":
        bit = self.n - 1 - q
        mask = 1 << bit
        N = 2 ** self.n
        new: Vector = list(self.state)
        u00, u01 = U[0][0], U[0][1]
        u10, u11 = U[1][0], U[1][1]
        for i in range(N):
            if i & mask: continue
            j = i | mask
            a, b = self.state[i], self.state[j]
            new[i] = u00 * a + u01 * b
            new[j] = u10 * a + u11 * b
        self.state = new
        self.history.append(f"apply({_gate_name(U)}, q={q})")
        return self

    # v13.14: sparse CNOT — O(N), no matrix build
    def cnot(self, control: int, target: int) -> "QuantumLane":
        if control == target: raise ValueError("control != target")
        cbit = self.n - 1 - control
        tbit = self.n - 1 - target
        cmask, tmask = 1 << cbit, 1 << tbit
        new: Vector = list(self.state)
        for i in range(2 ** self.n):
            if not (i & cmask): continue
            j = i ^ tmask
            if i < j:
                new[i], new[j] = self.state[j], self.state[i]
        self.state = new
        self.history.append(f"cnot(c={control}, t={target})")
        return self

    # v13.14: new gates ─────────────────────────────────────────────────
    def cz(self, control: int, target: int) -> "QuantumLane":
        """Controlled-Z: phase-flip when both control and target are |1>."""
        if control == target: raise ValueError("control != target")
        cbit = self.n - 1 - control
        tbit = self.n - 1 - target
        cmask, tmask = 1 << cbit, 1 << tbit
        for i in range(2 ** self.n):
            if (i & cmask) and (i & tmask):
                self.state[i] = -self.state[i]
        self.history.append(f"cz(c={control}, t={target})")
        return self

    def swap(self, a: int, b: int) -> "QuantumLane":
        if a == b: return self
        abit, bbit = self.n - 1 - a, self.n - 1 - b
        amask, bmask = 1 << abit, 1 << bbit
        new = list(self.state)
        for i in range(2 ** self.n):
            ba = (i >> abit) & 1
            bb = (i >> bbit) & 1
            if ba == bb: continue
            # swap means flip both bits to swap their values
            j = i ^ amask ^ bmask
            if i < j:
                new[i], new[j] = self.state[j], self.state[i]
        self.state = new
        self.history.append(f"swap({a}, {b})")
        return self

    def toffoli(self, c1: int, c2: int, target: int) -> "QuantumLane":
        """CCNOT: flip target iff both controls are |1>."""
        for x in (c1, c2, target):
            if x < 0 or x >= self.n: raise ValueError("qubit out of range")
        if len({c1, c2, target}) != 3: raise ValueError("c1, c2, target must be distinct")
        c1b, c2b, tb = self.n - 1 - c1, self.n - 1 - c2, self.n - 1 - target
        c1m, c2m, tm = 1 << c1b, 1 << c2b, 1 << tb
        new = list(self.state)
        for i in range(2 ** self.n):
            if (i & c1m) and (i & c2m):
                j = i ^ tm
                if i < j:
                    new[i], new[j] = self.state[j], self.state[i]
        self.state = new
        self.history.append(f"toffoli({c1}, {c2}, {target})")
        return self

    def ccz(self, c1: int, c2: int, target: int) -> "QuantumLane":
        """CCZ: phase flip when c1, c2, target are all |1>."""
        c1b, c2b, tb = self.n - 1 - c1, self.n - 1 - c2, self.n - 1 - target
        c1m, c2m, tm = 1 << c1b, 1 << c2b, 1 << tb
        for i in range(2 ** self.n):
            if (i & c1m) and (i & c2m) and (i & tm):
                self.state[i] = -self.state[i]
        self.history.append(f"ccz({c1}, {c2}, {target})")
        return self

    # ── observables ─────────────────────────────────────────────────────
    def probabilities(self) -> Dict[str, float]:
        probs: Dict[str, float] = {}
        for i, amp in enumerate(self.state):
            p = (amp.real * amp.real + amp.imag * amp.imag)
            probs[format(i, f"0{self.n}b")] = p
        return probs

    def measure(self, shots: int = 1024, rng: Optional[random.Random] = None) -> Dict[str, int]:
        rng = rng or random.Random()
        probs = self.probabilities()
        keys = list(probs.keys())
        weights = [probs[k] for k in keys]
        # normalize for numerical hygiene
        s = sum(weights)
        if s > 0:
            weights = [w / s for w in weights]
        # cumulative
        cum: List[float] = []
        running = 0.0
        for w in weights:
            running += w; cum.append(running)
        counts: Dict[str, int] = {}
        for _ in range(shots):
            r = rng.random()
            for idx, c in enumerate(cum):
                if r <= c:
                    k = keys[idx]; counts[k] = counts.get(k, 0) + 1; break
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def expectation(self, observable: str = "ZZ") -> float:
        if len(observable) != self.n:
            raise ValueError(f"observable length {len(observable)} != n_qubits {self.n}")
        ops: List[Matrix] = []
        for ch in observable.upper():
            if   ch == "I": ops.append(Gates.I)
            elif ch == "X": ops.append(Gates.X)
            elif ch == "Y": ops.append(Gates.Y)
            elif ch == "Z": ops.append(Gates.Z)
            else: raise ValueError(f"bad pauli letter: {ch}")
        full = ops[0]
        for op in ops[1:]:
            full = _kron(full, op)
        Ov = _matvec(full, self.state)
        # <psi|O|psi> = sum conj(psi[i]) * Ov[i]
        s = Complex(0, 0)
        for i in range(len(self.state)):
            s += self.state[i].conjugate() * Ov[i]
        return float(s.real)

    def state_str(self, decimals: int = 3) -> str:
        parts: List[str] = []
        for i, amp in enumerate(self.state):
            if abs(amp) < 1e-9: continue
            key = format(i, f"0{self.n}b")
            r, im = amp.real, amp.imag
            if abs(im) < 1e-9:
                parts.append(f"{r:+.{decimals}f}|{key}>")
            elif abs(r) < 1e-9:
                parts.append(f"{im:+.{decimals}f}i|{key}>")
            else:
                parts.append(f"({r:+.{decimals}f}{im:+.{decimals}f}i)|{key}>")
        return " ".join(parts) if parts else "0"

    # ── prebaked experiments ────────────────────────────────────────────
    @staticmethod
    def bell_pair() -> "QuantumLane":
        q = QuantumLane(2)
        q.apply(Gates.H, 0).cnot(0, 1)
        return q

    @staticmethod
    def ghz_triplet() -> "QuantumLane":
        q = QuantumLane(3)
        q.apply(Gates.H, 0).cnot(0, 1).cnot(0, 2)
        return q

    @staticmethod
    def quantum_coin() -> "QuantumLane":
        q = QuantumLane(1)
        q.apply(Gates.H, 0)
        return q
