"""Density matrix representation + sparse single-qubit operations.

ρ is N×N complex (N = 2**n_qubits). Pure state: ρ = |ψ⟩⟨ψ|. Mixed state:
ρ = Σ p_i |ψ_i⟩⟨ψ_i|, with Tr(ρ) = 1 and ρ Hermitian positive-semidefinite.

Applying a 1-qubit unitary U to qubit q on an n-qubit density matrix:
  ρ → U_q ρ U_q†, where U_q = I ⊗ ... ⊗ U ⊗ ... ⊗ I

We do it sparsely: row-pass with U then column-pass with U†, each O(N²)
instead of the O(N³) of full matrix multiply.
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

Complex = complex


def _new_rho(N: int) -> List[List[Complex]]:
    return [[Complex(0, 0)] * N for _ in range(N)]


class DensityMatrix:
    MAX_QUBITS = 6   # density matrices are 2^n × 2^n — 6 qubits = 64×64 = 4096 cells

    def __init__(self, n_qubits: int) -> None:
        if not 1 <= n_qubits <= self.MAX_QUBITS:
            raise ValueError(f"n_qubits must be 1..{self.MAX_QUBITS}")
        self.n = n_qubits
        N = 2 ** n_qubits
        self.rho: List[List[Complex]] = _new_rho(N)
        self.rho[0][0] = Complex(1, 0)
        self.history: List[str] = []

    @staticmethod
    def from_state_vector(psi: List[Complex], n_qubits: int) -> "DensityMatrix":
        dm = DensityMatrix(n_qubits)
        N = 2 ** n_qubits
        if len(psi) != N: raise ValueError("psi length mismatch")
        dm.rho = [[psi[i] * psi[j].conjugate() for j in range(N)] for i in range(N)]
        return dm

    # ── sparse single-qubit unitary on qubit q ───────────────────────────
    def apply_unitary_1q(self, U: List[List[Complex]], q: int) -> "DensityMatrix":
        N = 2 ** self.n
        bit = self.n - 1 - q
        mask = 1 << bit
        u00, u01 = U[0][0], U[0][1]
        u10, u11 = U[1][0], U[1][1]
        # Step 1: ρ → U_q ρ (apply U to each COLUMN as a state vector)
        for c in range(N):
            for i in range(N):
                if i & mask: continue
                j = i | mask
                a, b = self.rho[i][c], self.rho[j][c]
                self.rho[i][c] = u00 * a + u01 * b
                self.rho[j][c] = u10 * a + u11 * b
        # Step 2: ρ → ρ U_q† (apply U* to each ROW)
        u00c, u01c = u00.conjugate(), u01.conjugate()
        u10c, u11c = u10.conjugate(), u11.conjugate()
        for r in range(N):
            for i in range(N):
                if i & mask: continue
                j = i | mask
                a, b = self.rho[r][i], self.rho[r][j]
                self.rho[r][i] = a * u00c + b * u01c
                self.rho[r][j] = a * u10c + b * u11c
        self.history.append(f"U_1q(q={q})")
        return self

    def apply_cnot(self, control: int, target: int) -> "DensityMatrix":
        """Sparse CNOT: swap rows AND columns of ρ where control bit = 1."""
        N = 2 ** self.n
        cbit, tbit = self.n - 1 - control, self.n - 1 - target
        cmask, tmask = 1 << cbit, 1 << tbit
        # row permutation
        for i in range(N):
            if not (i & cmask): continue
            j = i ^ tmask
            if i < j:
                self.rho[i], self.rho[j] = self.rho[j], self.rho[i]
        # column permutation
        for r in range(N):
            for i in range(N):
                if not (i & cmask): continue
                j = i ^ tmask
                if i < j:
                    self.rho[r][i], self.rho[r][j] = self.rho[r][j], self.rho[r][i]
        self.history.append(f"CNOT(c={control},t={target})")
        return self

    # ── sparse Kraus channel on qubit q ─────────────────────────────────
    def apply_kraus_1q(self, kraus_ops: List[List[List[Complex]]], q: int,
                       label: str = "channel") -> "DensityMatrix":
        """ρ → Σ_k K_k ρ K_k† for a list of 1-qubit Kraus operators on qubit q.
        Each K_k must satisfy Σ K_k† K_k = I."""
        N = 2 ** self.n
        bit = self.n - 1 - q
        mask = 1 << bit
        new = _new_rho(N)
        for K in kraus_ops:
            k00, k01 = K[0][0], K[0][1]
            k10, k11 = K[1][0], K[1][1]
            k00c, k01c = k00.conjugate(), k01.conjugate()
            k10c, k11c = k10.conjugate(), k11.conjugate()
            # tmp = K ρ
            tmp = [row[:] for row in self.rho]
            for c in range(N):
                for i in range(N):
                    if i & mask: continue
                    j = i | mask
                    a, b = self.rho[i][c], self.rho[j][c]
                    tmp[i][c] = k00 * a + k01 * b
                    tmp[j][c] = k10 * a + k11 * b
            # tmp2 = tmp K†; accumulate into new
            for r in range(N):
                for i in range(N):
                    if i & mask: continue
                    j = i | mask
                    a, b = tmp[r][i], tmp[r][j]
                    new[r][i] += a * k00c + b * k01c
                    new[r][j] += a * k10c + b * k11c
        self.rho = new
        self.history.append(f"{label}(q={q})")
        return self

    # ── observables ─────────────────────────────────────────────────────
    def trace(self) -> Complex:
        return sum(self.rho[i][i] for i in range(2 ** self.n))

    def normalize(self) -> "DensityMatrix":
        t = self.trace()
        if abs(t) < 1e-12: return self
        N = 2 ** self.n
        for i in range(N):
            for j in range(N):
                self.rho[i][j] = self.rho[i][j] / t
        return self

    def expectation(self, observable_letters: str) -> float:
        """<O> = Tr(Oρ) for tensor of single-qubit Pauli letters (I,X,Y,Z)."""
        from src.tower.research_floor.quantum_triad_sandbox.quantum_lane import Gates, _kron
        if len(observable_letters) != self.n:
            raise ValueError(f"observable length {len(observable_letters)} != n_qubits {self.n}")
        ops: List[List[List[Complex]]] = []
        for ch in observable_letters.upper():
            if   ch == "I": ops.append(Gates.I)
            elif ch == "X": ops.append(Gates.X)
            elif ch == "Y": ops.append(Gates.Y)
            elif ch == "Z": ops.append(Gates.Z)
            else: raise ValueError(f"bad pauli letter: {ch}")
        full = ops[0]
        for op in ops[1:]:
            full = _kron(full, op)
        N = 2 ** self.n
        s = Complex(0, 0)
        # Tr(O ρ) = Σ_i,k O[i,k] ρ[k,i]
        for i in range(N):
            for k in range(N):
                if full[i][k] == 0: continue
                s += full[i][k] * self.rho[k][i]
        return float(s.real)

    def probabilities(self) -> Dict[str, float]:
        """Diagonal of ρ = probabilities of computational-basis outcomes."""
        N = 2 ** self.n
        return {format(i, f"0{self.n}b"): float(self.rho[i][i].real) for i in range(N)}

    def purity(self) -> float:
        """Tr(ρ²). Pure → 1. Maximally mixed → 1/N."""
        N = 2 ** self.n
        s = 0.0
        for i in range(N):
            for j in range(N):
                aij = self.rho[i][j]
                # (ρ²)[i,i] = Σ_j ρ[i,j] ρ[j,i] = Σ_j ρ[i,j] · conjugate(ρ[i,j]) for Hermitian ρ
                # because ρ[j,i] = ρ[i,j]* for Hermitian
                s += (aij.real * aij.real + aij.imag * aij.imag)
        return float(s)

    def partial_trace(self, keep_qubits: List[int]) -> "DensityMatrix":
        """Tr_{traced-out qubits} ρ → reduced density matrix on `keep_qubits`."""
        keep = sorted(keep_qubits)
        trace_out = [q for q in range(self.n) if q not in keep]
        N = 2 ** self.n
        N_keep = 2 ** len(keep)
        N_out = 2 ** len(trace_out)
        new_rho = _new_rho(N_keep)
        # Iterate over all basis indices; split each into (keep_idx, out_idx)
        keep_bits = [self.n - 1 - q for q in keep]
        out_bits = [self.n - 1 - q for q in trace_out]
        for i in range(N):
            ik = 0; io_i = 0
            for pos, b in enumerate(keep_bits): ik |= ((i >> b) & 1) << (len(keep) - 1 - pos)
            for pos, b in enumerate(out_bits):  io_i |= ((i >> b) & 1) << (len(trace_out) - 1 - pos)
            for j in range(N):
                jk = 0; io_j = 0
                for pos, b in enumerate(keep_bits): jk |= ((j >> b) & 1) << (len(keep) - 1 - pos)
                for pos, b in enumerate(out_bits):  io_j |= ((j >> b) & 1) << (len(trace_out) - 1 - pos)
                if io_i == io_j:
                    new_rho[ik][jk] += self.rho[i][j]
        reduced = DensityMatrix(len(keep))
        reduced.rho = new_rho
        return reduced

    def von_neumann_entropy(self) -> float:
        """S(ρ) = -Tr(ρ log₂ ρ). Computed via eigenvalues using power iteration.
        For small ρ (≤ 6 qubits), we use a numerically stable method on the
        Hermitian matrix via Jacobi-style iteration."""
        # Quick + dirty: use the eigenvalue decomposition via QR-like iteration
        # is overkill in pure Python. Instead we use the fact that we only need
        # eigenvalues, not eigenvectors, and ρ is small (≤ 64×64). We use
        # the power-iteration-deflation approach.
        N = 2 ** self.n
        # Build a flat list-of-lists copy as floats (real + imag pairs flattened)
        # then do Jacobi-rotation for Hermitian eigenvalues.
        evals = _hermitian_eigenvalues(self.rho, N)
        s = 0.0
        for ev in evals:
            ev = max(0.0, ev)   # numerical floor
            if ev > 1e-12:
                s -= ev * math.log2(ev)
        return s


# ─────────────────────────────────────────────────────────────────────────
# Jacobi eigenvalue solver for a small Hermitian complex matrix
# ─────────────────────────────────────────────────────────────────────────
def _hermitian_eigenvalues(H: List[List[Complex]], N: int,
                            max_sweeps: int = 100, tol: float = 1e-10) -> List[float]:
    """Eigenvalues of an N×N Hermitian matrix via Jacobi rotations.
    Works in pure Python on lists of complex. For small N (≤ 64) this is fast
    enough."""
    # Copy
    A = [row[:] for row in H]
    for sweep in range(max_sweeps):
        off = 0.0
        for i in range(N):
            for j in range(i + 1, N):
                aij = A[i][j]
                off += aij.real * aij.real + aij.imag * aij.imag
        if off < tol * tol:
            break
        # Find largest off-diagonal
        p, q, big = 0, 1, 0.0
        for i in range(N):
            for j in range(i + 1, N):
                m = A[i][j].real * A[i][j].real + A[i][j].imag * A[i][j].imag
                if m > big:
                    big = m; p, q = i, j
        # Jacobi rotation on real-symmetric block; for complex Hermitian use the
        # standard formula: phase out A[p,q] then real Jacobi.
        # Compute phase
        a_pq = A[p][q]
        mag = math.sqrt(a_pq.real * a_pq.real + a_pq.imag * a_pq.imag)
        if mag < 1e-14: break
        phase = a_pq / mag
        # Build rotation matrix R = diag(I) with 2x2 block:
        #   [[c, -s·phase*], [s/phase, c]]
        diff = A[q][q].real - A[p][p].real
        if abs(diff) < 1e-14:
            theta = math.pi / 4
        else:
            theta = 0.5 * math.atan2(2.0 * mag, diff)
        c, s = math.cos(theta), math.sin(theta)
        # Apply rotation to rows p, q
        for k in range(N):
            akp, akq = A[k][p], A[k][q]
            A[k][p] = c * akp - s * akq * phase.conjugate()
            A[k][q] = s * akp * phase + c * akq
        # Apply rotation to columns p, q
        for k in range(N):
            apk, aqk = A[p][k], A[q][k]
            A[p][k] = c * apk - s * phase * aqk
            A[q][k] = s * phase.conjugate() * apk + c * aqk
    return [A[i][i].real for i in range(N)]
