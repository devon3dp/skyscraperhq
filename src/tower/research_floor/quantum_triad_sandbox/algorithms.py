"""Canonical quantum algorithms + tests as TriadQuery experiments.

Built on top of QuantumLane / ClassicalLane / CognitiveLane.
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional

from .quantum_lane import QuantumLane, Gates
from .classical_lane import ClassicalLane
from .cognitive_lane import CognitiveLane
from .safety import envelope


# ─────────────────────────────────────────────────────────────────────────
# CHSH / Bell inequality test
# ─────────────────────────────────────────────────────────────────────────
def _bell_pair_with_measurement_angles(theta_a: float, theta_b: float) -> QuantumLane:
    """Prepare Bell pair, then rotate each qubit to its measurement basis.

    Bloch-angle convention: measuring along axis cos(θ)·Z + sin(θ)·X is done
    by applying ry(-θ) to the qubit, then measuring Z. (Verified by
    <0|ry(θ)·Z·ry(-θ)|0> = cos(θ).)
    """
    q = QuantumLane.bell_pair()
    q.apply(Gates.ry(-theta_a), 0)
    q.apply(Gates.ry(-theta_b), 1)
    return q


def _correlation_E(theta_a: float, theta_b: float, shots: int) -> float:
    """E(a,b) = <σa ⊗ σb> for Bell pair measured at angles θa, θb."""
    q = _bell_pair_with_measurement_angles(theta_a, theta_b)
    return q.expectation("ZZ")


def chsh_test(shots: int = 4000) -> Dict:
    """Canonical CHSH inequality test.

    For a Bell state and measurement angles
        a0 = 0,     a1 = π/2
        b0 = π/4,   b1 = -π/4
    the CHSH quantity
        S = E(a0,b0) - E(a0,b1) + E(a1,b0) + E(a1,b1)
    satisfies S ≤ 2 for ALL classical local-hidden-variable theories
    and reaches S = 2√2 ≈ 2.828 for the Bell pair. That excess proves
    quantum cannot be explained by ANY local hidden variable model.
    """
    # Bloch-angle CHSH optimum for |Φ+>:
    #   a0 = 0, a1 = π/2;  b0 = π/4, b1 = 3π/4
    # gives S = 2√2 ≈ 2.828
    a0 = 0.0
    a1 = math.pi / 2
    b0 = math.pi / 4
    b1 = 3 * math.pi / 4

    E00 = _correlation_E(a0, b0, shots)
    E01 = _correlation_E(a0, b1, shots)
    E10 = _correlation_E(a1, b0, shots)
    E11 = _correlation_E(a1, b1, shots)
    S = E00 - E01 + E10 + E11

    classical_bound = 2.0
    quantum_max = 2.0 * math.sqrt(2.0)
    violates = abs(S) > classical_bound + 1e-6

    # Classical lane: shared-randomness model max
    c = ClassicalLane.deterministic_bell_analog()
    classical_S_imitation = 2.0  # the maximum achievable by any LHV

    cog = CognitiveLane().consult(
        "CHSH inequality violation — does the Bell pair beat 2.0?")

    return {
        "envelope": envelope(),
        "question": "CHSH inequality (Bell test)",
        "quantum": {
            "E(a0,b0)": E00, "E(a0,b1)": E01,
            "E(a1,b0)": E10, "E(a1,b1)": E11,
            "S": S,
            "violates_classical_bound": violates,
            "quantum_maximum": quantum_max,
        },
        "classical": {
            "S_maximum_for_any_LHV": classical_S_imitation,
            "note": "no local-hidden-variable model can reach S > 2.",
        },
        "cognitive": cog,
        "verdict": (
            f"S = {S:.4f}. "
            f"Classical bound: |S| ≤ 2. "
            f"Quantum maximum: 2√2 ≈ {quantum_max:.4f}. "
            + ("VIOLATED — no LHV theory can reproduce this." if violates
               else "No violation in this run.")
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# Grover's search
# ─────────────────────────────────────────────────────────────────────────
def grover_search(n_qubits: int = 3, target: int = 5, shots: int = 2000) -> Dict:
    """Grover's algorithm on n qubits searching for a single marked target.

    The marked state has its amplitude inverted; then the diffusion operator
    reflects all amplitudes about their mean. After about (π/4)·√N iterations,
    the marked state's amplitude is amplified close to 1.

    Classical search is O(N). Grover is O(√N).
    """
    if not 1 <= n_qubits <= 6:
        raise ValueError("Grover toy: n_qubits in 1..6")
    N = 2 ** n_qubits
    if not 0 <= target < N:
        raise ValueError(f"target must be 0..{N - 1}")

    # iteration count for highest success probability
    iterations = max(1, round((math.pi / 4) * math.sqrt(N)))

    q = QuantumLane(n_qubits)
    # 1. uniform superposition: H on every qubit
    for i in range(n_qubits):
        q.apply(Gates.H, i)

    # 2. Grover iterations
    for _ in range(iterations):
        # Oracle: phase-flip the target by setting amplitude[target] = -amplitude[target]
        q.state[target] = -q.state[target]
        q.history.append(f"oracle(mark={target:0{n_qubits}b})")
        # Diffusion: 2|s><s| - I where |s> = uniform superposition
        # In computational basis: 2·avg - psi[i]  (when applied to each amplitude
        # of the H^n |0> reference)
        # Standard implementation: H on all → reflect about |0> → H on all
        for i in range(n_qubits):
            q.apply(Gates.H, i)
        # reflect about |0...0>: flip sign of every amplitude EXCEPT |0...0>
        for i in range(N):
            if i != 0:
                q.state[i] = -q.state[i]
        q.history.append("reflect_about_0")
        for i in range(n_qubits):
            q.apply(Gates.H, i)
        q.history.append("diffusion")

    target_str = format(target, f"0{n_qubits}b")
    probs = q.probabilities()
    p_target = probs.get(target_str, 0.0)
    counts = q.measure(shots=shots)
    classical_baseline = 1.0 / N

    cog = CognitiveLane().consult(
        f"Grover search for {target_str} on {n_qubits} qubits")

    return {
        "envelope": envelope(),
        "question": f"Grover search · target={target_str} · {n_qubits} qubits",
        "quantum": {
            "n_qubits": n_qubits,
            "target": target_str,
            "iterations_used": iterations,
            "p(target)_after_grover": p_target,
            "classical_random_baseline": classical_baseline,
            "speedup_amplitude_ratio": p_target / classical_baseline if classical_baseline > 0 else None,
            "measurement_top": dict(list(counts.items())[:5]),
        },
        "classical": {
            "p(any_specific_outcome)_random": classical_baseline,
            "expected_queries_to_find_target_classical": N // 2,
            "expected_queries_grover": iterations,
            "note": f"classical: O(N)={N}; grover: O(√N)≈{int(math.sqrt(N))} (quadratic speedup)",
        },
        "cognitive": cog,
        "verdict": (
            f"p(target) = {p_target:.4f} after {iterations} iterations. "
            f"Classical random baseline = {classical_baseline:.4f}. "
            f"Amplification ratio: {p_target / classical_baseline:.1f}x"
            if classical_baseline > 0 else ""
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# ASCII probability bars
# ─────────────────────────────────────────────────────────────────────────
def probability_bars(probs: Dict[str, float], width: int = 40, threshold: float = 0.001) -> str:
    """Render a probability distribution as ASCII bars."""
    lines: List[str] = []
    items = sorted(probs.items())
    for key, p in items:
        if p < threshold:
            continue
        bar_len = int(round(p * width))
        bar = "█" * bar_len
        lines.append(f"  |{key}>  {bar:<{width}}  {p * 100:6.2f}%")
    if not lines:
        return "  (all probabilities below threshold)"
    return "\n".join(lines)
