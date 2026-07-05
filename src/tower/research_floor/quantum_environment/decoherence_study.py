"""Canonical decoherence experiments — watch quantum advantage decay.

Each study compares the closed-system result (no noise) to the open-system
result (noise inserted). The interesting physics is in the gradient.
"""
from __future__ import annotations
import math
from typing import Dict, List

from .density import DensityMatrix
from .open_system import NoisyCircuit
from .channels import depolarizing, amplitude_damping, phase_damping, identity_channel


# ── Bell pair under increasing depolarizing noise ────────────────────────
def bell_decay_study(noise_levels: List[float] = None) -> Dict:
    """Prepare a Bell pair, apply depolarizing noise at increasing strengths,
    measure <XX>, <YY>, <ZZ>, purity, and entropy of one qubit.

    Closed Bell state (no noise): <XX> = <ZZ> = 1, <YY> = -1, purity = 1.
    As noise increases, all correlations shrink toward 0; purity drops to
    1/4 (maximally mixed); single-qubit entropy rises from 1 (Bell pair is
    a maximally entangled pair → each qubit alone is maximally mixed) toward
    1 (when full system is mixed, partial trace stays maximally mixed).
    """
    from .concurrence import concurrence
    levels = noise_levels or [0.0, 0.05, 0.10, 0.20, 0.40, 0.75, 1.0]
    rows: List[Dict] = []
    for p in levels:
        nc = NoisyCircuit(2,
                          channel_factory=(lambda p=p: depolarizing(p)),
                          channel_label=f"depol(p={p:.2f})")
        nc.add("H", "0").add("CNOT", "0", "1")
        nc.run()
        xx = nc.measure_observable("XX")
        yy = nc.measure_observable("YY")
        zz = nc.measure_observable("ZZ")
        pur = nc.dm.purity()
        ent_q0 = nc.dm.partial_trace([0]).von_neumann_entropy()
        ent_total = nc.dm.von_neumann_entropy()       # v13.16: full system S
        conc = concurrence(nc.dm)                       # v13.16: entanglement measure
        rows.append({
            "noise_p": p,
            "<XX>":   xx, "<YY>": yy, "<ZZ>": zz,
            "bell_fidelity": (xx - yy + zz + 1.0) / 4.0,
            "purity": pur,
            "q0_entropy_bits": ent_q0,
            "total_entropy_bits": ent_total,
            "concurrence": conc,
        })
    return {
        "experiment": "Bell pair under depolarizing noise — full diagnostic (v13.16)",
        "rows": rows,
        "verdict": (
            "Five diagnostics tell different parts of the same story:\n"
            "  · ⟨XX⟩,⟨YY⟩,⟨ZZ⟩ shrink to 0 — coherence dies\n"
            "  · purity falls 1 → 1/4 — state mixes\n"
            "  · q0 subsystem S STAYS at 1.0 — symmetric noise + entanglement\n"
            "  · TOTAL S rises 0 → 2 bits — full system loses information\n"
            "  · concurrence falls 1 → 0 — entanglement quantitatively dies\n"
            "Any single column hides the picture. The triad needed a quintet."
        ),
    }


# ── CHSH violation eroded by noise ───────────────────────────────────────
def chsh_under_noise_study(noise_levels: List[float] = None) -> Dict:
    """CHSH S as a function of single-qubit depolarizing noise applied between
    state prep and measurement.

    Closed: S = 2√2.  At noise p, expected S = 2√2 · (1-p) · (1-p) — the
    correlations get multiplied by (1-p) per qubit. So CHSH crosses the
    classical bound S=2 around p ≈ 1 - 1/sqrt(√2) ≈ 0.157 per qubit.
    """
    from src.tower.research_floor.quantum_triad_sandbox.quantum_lane import Gates

    levels = noise_levels or [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75]
    angles = {
        ("a0", 0.0):           ("a0", 0.0),
        ("a1", math.pi / 2):   ("a1", math.pi / 2),
        ("b0", math.pi / 4):   ("b0", math.pi / 4),
        ("b1", 3 * math.pi / 4): ("b1", 3 * math.pi / 4),
    }
    a0, a1 = 0.0, math.pi / 2
    b0, b1 = math.pi / 4, 3 * math.pi / 4
    rows: List[Dict] = []
    classical_bound = 2.0
    tsirelson = 2.0 * math.sqrt(2.0)

    def _S(p: float) -> Dict:
        def E(th_a: float, th_b: float) -> float:
            nc = NoisyCircuit(2,
                              channel_factory=(lambda p=p: depolarizing(p)),
                              channel_label=f"depol(p={p:.2f})")
            nc.add("H", "0").add("CNOT", "0", "1")
            nc.add("RY", "0", f"{-th_a}").add("RY", "1", f"{-th_b}")
            nc.run()
            return nc.measure_observable("ZZ")
        E00 = E(a0, b0); E01 = E(a0, b1)
        E10 = E(a1, b0); E11 = E(a1, b1)
        S = E00 - E01 + E10 + E11
        return {"E00": E00, "E01": E01, "E10": E10, "E11": E11, "S": S}

    for p in levels:
        r = _S(p)
        rows.append({
            "noise_p": p,
            **r,
            "violates_classical": abs(r["S"]) > classical_bound + 1e-6,
            "fraction_of_tsirelson": abs(r["S"]) / tsirelson,
        })
    return {
        "experiment": "CHSH violation eroded by depolarizing noise on both qubits",
        "rows": rows,
        "classical_bound": classical_bound,
        "tsirelson_bound": tsirelson,
        "verdict": (
            f"S(p=0) = 2√2 ≈ {tsirelson:.4f} (Tsirelson). "
            "As p increases, S falls. The crossover where S drops below 2 "
            "(loses violation) marks the noise threshold where the system "
            "becomes 'classically simulatable' — no LHV needed."
        ),
    }


# ── Grover under noise ───────────────────────────────────────────────────
def grover_under_noise_study(n_qubits: int = 3, target: int = 5,
                              noise_levels: List[float] = None) -> Dict:
    """Grover's success probability under depolarizing noise on every qubit
    after every gate. Quantum advantage degrades smoothly with p."""
    from src.tower.research_floor.quantum_triad_sandbox.quantum_lane import Gates

    levels = noise_levels or [0.0, 0.01, 0.05, 0.10, 0.20]
    N = 2 ** n_qubits
    iterations = max(1, round((math.pi / 4) * math.sqrt(N)))
    target_str = format(target, f"0{n_qubits}b")
    classical_baseline = 1.0 / N

    rows: List[Dict] = []
    for p in levels:
        nc = NoisyCircuit(n_qubits,
                          channel_factory=(lambda p=p: depolarizing(p)),
                          channel_label=f"depol(p={p:.2f})")
        # 1. Uniform superposition
        for q in range(n_qubits):
            nc.add("H", str(q))
        # 2. v13.16: REAL Grover iterations using new PHASE_FLIP + REFLECT_ABOUT_ZERO
        for _ in range(iterations):
            nc.add("PHASE_FLIP", str(target))             # oracle
            for q in range(n_qubits): nc.add("H", str(q))
            nc.add("REFLECT_ABOUT_ZERO")                  # diffusion middle
            for q in range(n_qubits): nc.add("H", str(q))
        nc.run()
        probs = nc.probabilities()
        p_t = probs.get(target_str, 0.0)
        rows.append({
            "noise_p": p,
            "p(target)": p_t,
            "classical_baseline": classical_baseline,
            "advantage_ratio": (p_t / classical_baseline) if classical_baseline > 0 else None,
            "purity": nc.dm.purity(),
        })
    return {
        "experiment": f"Grover (n={n_qubits}, target={target_str}) under noise — REAL oracle (v13.16)",
        "iterations_used": iterations,
        "rows": rows,
        "verdict": (
            "v13.16 uses the REAL Grover oracle via PHASE_FLIP + REFLECT_ABOUT_ZERO. "
            "The previous simplified-H-sandwich model is retired. p=0 should give "
            "≥99% success; noise degrades this smoothly."
        ),
    }
