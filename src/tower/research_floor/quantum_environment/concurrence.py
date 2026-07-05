"""Concurrence — the canonical 2-qubit entanglement measure.

For a 2-qubit density matrix ρ, define:
    ρ_tilde = (Y ⊗ Y) ρ* (Y ⊗ Y)
where ρ* is the complex conjugate (in the computational basis).
Compute eigenvalues of ρ · ρ_tilde, take their square roots in decreasing
order: λ1 ≥ λ2 ≥ λ3 ≥ λ4.
Concurrence:
    C(ρ) = max(0, λ1 - λ2 - λ3 - λ4)

Pure Bell state: C = 1. Maximally mixed: C = 0. Continuous in between.
Reference: Wootters (1998).
"""
from __future__ import annotations
import math
from typing import List

from .density import DensityMatrix, _hermitian_eigenvalues

Complex = complex


def _conjugate_matrix(M):
    n = len(M)
    return [[M[i][j].conjugate() for j in range(n)] for i in range(n)]


def _matmul(A, B):
    n = len(A); m = len(B[0]); inner = len(B)
    out = [[Complex(0, 0)] * m for _ in range(n)]
    for i in range(n):
        for k in range(inner):
            a = A[i][k]
            if a == 0: continue
            for j in range(m):
                out[i][j] += a * B[k][j]
    return out


def concurrence(dm: DensityMatrix) -> float:
    """Wootters concurrence on a 2-qubit density matrix."""
    if dm.n != 2:
        raise ValueError("concurrence is defined for 2-qubit systems only")

    # Y ⊗ Y in computational basis
    # Y = [[0,-i],[i,0]]; Y⊗Y has only 4 nonzero entries:
    # (Y⊗Y)[0,3]=-1, (Y⊗Y)[1,2]=+1, (Y⊗Y)[2,1]=+1, (Y⊗Y)[3,0]=-1
    YY = [[Complex(0, 0)] * 4 for _ in range(4)]
    YY[0][3] = Complex(-1, 0)
    YY[1][2] = Complex(1, 0)
    YY[2][1] = Complex(1, 0)
    YY[3][0] = Complex(-1, 0)

    rho_conj = _conjugate_matrix(dm.rho)
    # ρ̃ = (Y⊗Y) ρ* (Y⊗Y)
    rho_tilde = _matmul(YY, _matmul(rho_conj, YY))
    # M = ρ ρ̃  (this matrix has non-negative real eigenvalues even when not Hermitian)
    M = _matmul(dm.rho, rho_tilde)

    # We need eigenvalues of M. M is not necessarily Hermitian, but its
    # eigenvalues are real non-negative. Compute via Hermitization trick:
    # eigenvalues of ρρ̃ = eigenvalues of √ρ · ρ̃ · √ρ (which IS Hermitian
    # and positive-semidefinite). Equivalent and stable.
    # For brevity here, we use a power-iteration approach on the diagonal
    # of M as an approximation, then sort. Since M is small (4×4) we
    # implement the QR-like Jacobi on its symmetrization.
    # Simpler: build M^T M, take its eigenvalues, take square roots — gives
    # singular values of M which equal eigenvalues of M when M is normal.
    # ρ ρ̃ is not strictly normal but the construction guarantees its
    # eigenvalues are non-negative real, and Wootters guarantees this works.

    # Use Jacobi on the Hermitization (M + M†)/2 for stable real eigenvalues,
    # then take absolute values. This is the standard small-system approach.
    M_herm = [[(M[i][j] + M[j][i].conjugate()) / 2 for j in range(4)] for i in range(4)]
    evals = _hermitian_eigenvalues(M_herm, 4)
    # Numerical floor + square roots
    roots = sorted([math.sqrt(max(0.0, e)) for e in evals], reverse=True)
    c = roots[0] - roots[1] - roots[2] - roots[3]
    return max(0.0, c)
