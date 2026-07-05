"""Kraus operators for canonical single-qubit noise channels.

Each function returns a list of 2×2 complex matrices whose Σ K_k† K_k = I.
Applied to a qubit q of a density matrix via DensityMatrix.apply_kraus_1q.

References: any quantum information textbook (e.g., Nielsen & Chuang ch. 8).
"""
from __future__ import annotations
import math
from typing import List

Complex = complex
Matrix = List[List[Complex]]


def identity_channel() -> List[Matrix]:
    """The no-op channel. Useful as a control case."""
    return [[
        [Complex(1, 0), Complex(0, 0)],
        [Complex(0, 0), Complex(1, 0)],
    ]]


def amplitude_damping(gamma: float) -> List[Matrix]:
    """Amplitude damping (T1 / spontaneous emission).
    γ ∈ [0,1]; γ=0 → identity, γ=1 → total decay to |0>.
        K0 = [[1, 0], [0, √(1-γ)]]
        K1 = [[0, √γ], [0, 0]]
    """
    if not 0.0 <= gamma <= 1.0:
        raise ValueError("gamma in [0,1]")
    s0 = math.sqrt(1.0 - gamma)
    s1 = math.sqrt(gamma)
    return [
        [[Complex(1, 0), Complex(0, 0)], [Complex(0, 0), Complex(s0, 0)]],
        [[Complex(0, 0), Complex(s1, 0)], [Complex(0, 0), Complex(0, 0)]],
    ]


def phase_damping(lam: float) -> List[Matrix]:
    """Phase damping (T2 / pure dephasing without energy loss).
    λ ∈ [0,1].
        K0 = [[1, 0], [0, √(1-λ)]]
        K1 = [[0, 0], [0, √λ]]
    """
    if not 0.0 <= lam <= 1.0:
        raise ValueError("lambda in [0,1]")
    s0 = math.sqrt(1.0 - lam)
    s1 = math.sqrt(lam)
    return [
        [[Complex(1, 0), Complex(0, 0)], [Complex(0, 0), Complex(s0, 0)]],
        [[Complex(0, 0), Complex(0, 0)], [Complex(0, 0), Complex(s1, 0)]],
    ]


def depolarizing(p: float) -> List[Matrix]:
    """Depolarizing channel: with probability p, replace ρ with maximally mixed.
    Kraus form on single qubit:
        K0 = √(1 - 3p/4) I,  K1 = √(p/4) X,  K2 = √(p/4) Y,  K3 = √(p/4) Z
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError("p in [0,1]")
    s_i = math.sqrt(1.0 - 3.0 * p / 4.0)
    s_xyz = math.sqrt(p / 4.0)
    I = [[Complex(s_i, 0), Complex(0, 0)], [Complex(0, 0), Complex(s_i, 0)]]
    X = [[Complex(0, 0), Complex(s_xyz, 0)], [Complex(s_xyz, 0), Complex(0, 0)]]
    Y = [[Complex(0, 0), Complex(0, -s_xyz)], [Complex(0, s_xyz), Complex(0, 0)]]
    Z = [[Complex(s_xyz, 0), Complex(0, 0)], [Complex(0, 0), Complex(-s_xyz, 0)]]
    return [I, X, Y, Z]


def bit_flip(p: float) -> List[Matrix]:
    """Bit flip with probability p. K0 = √(1-p) I, K1 = √p X."""
    if not 0.0 <= p <= 1.0: raise ValueError("p in [0,1]")
    s0 = math.sqrt(1.0 - p); s1 = math.sqrt(p)
    return [
        [[Complex(s0, 0), Complex(0, 0)], [Complex(0, 0), Complex(s0, 0)]],
        [[Complex(0, 0), Complex(s1, 0)], [Complex(s1, 0), Complex(0, 0)]],
    ]


def phase_flip(p: float) -> List[Matrix]:
    """Phase flip with probability p. K0 = √(1-p) I, K1 = √p Z."""
    if not 0.0 <= p <= 1.0: raise ValueError("p in [0,1]")
    s0 = math.sqrt(1.0 - p); s1 = math.sqrt(p)
    return [
        [[Complex(s0, 0), Complex(0, 0)], [Complex(0, 0), Complex(s0, 0)]],
        [[Complex(s1, 0), Complex(0, 0)], [Complex(0, 0), Complex(-s1, 0)]],
    ]
