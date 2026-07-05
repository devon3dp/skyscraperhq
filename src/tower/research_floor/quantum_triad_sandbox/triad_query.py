"""TriadQuery — the same question routed to all three lanes.

The point: lay three answers side by side. See where they agree, where they
diverge. Quantum lane gives probabilities + measurement statistics. Classical
lane gives the deterministic baseline (often the LHV imitation of the quantum
result). Cognitive lane brings F47's wisdom: refusal screen, aphorism, related
question.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import Dict, List, Optional

from .quantum_lane import QuantumLane
from .classical_lane import ClassicalLane
from .cognitive_lane import CognitiveLane
from .safety import envelope


LOG_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_research_quantum_triad_log.jsonl"


class TriadQuery:
    @staticmethod
    def bell_state_query(shots: int = 1024) -> Dict:
        q = QuantumLane.bell_pair()
        c = ClassicalLane.deterministic_bell_analog()
        cog = CognitiveLane().consult("are the bell pair correlations classically explainable?")
        return TriadQuery._format(
            question="Bell pair correlations — quantum vs LHV",
            quantum={
                "state": q.state_str(),
                "probabilities": q.probabilities(),
                "measurement_counts": q.measure(shots=shots),
                "expectation_ZZ": q.expectation("ZZ"),
                "expectation_XX": q.expectation("XX"),
                "history": q.history,
            },
            classical={
                "deterministic_value_a_run": c.value(),
                "sample_distribution": c.sample(shots=shots),
                "history": c.history,
                "note": "LHV imitation reproduces {00,11} statistics but no XX correlation",
            },
            cognitive=cog,
        )

    @staticmethod
    def ghz_query(shots: int = 1024) -> Dict:
        q = QuantumLane.ghz_triplet()
        c = ClassicalLane.deterministic_ghz_analog()
        cog = CognitiveLane().consult("three-particle entanglement: GHZ vs classical correlation")
        return TriadQuery._format(
            question="GHZ vs classical triple correlation",
            quantum={
                "state": q.state_str(),
                "probabilities": q.probabilities(),
                "measurement_counts": q.measure(shots=shots),
                "expectation_ZZZ": q.expectation("ZZZ"),
                "expectation_XXX": q.expectation("XXX"),
                "history": q.history,
            },
            classical={
                "deterministic_value_a_run": c.value(),
                "sample_distribution": c.sample(shots=shots),
                "history": c.history,
            },
            cognitive=cog,
        )

    @staticmethod
    def coin_query(shots: int = 1024) -> Dict:
        q = QuantumLane.quantum_coin()
        c = ClassicalLane.classical_coin()
        cog = CognitiveLane().consult("is a quantum coin different from a classical coin?")
        return TriadQuery._format(
            question="Coin flip — quantum (H|0>) vs classical RNG",
            quantum={
                "state": q.state_str(),
                "probabilities": q.probabilities(),
                "measurement_counts": q.measure(shots=shots),
                "expectation_Z": q.expectation("Z"),
                "expectation_X": q.expectation("X"),
                "note": "Z and X expectations together reveal coherence — classical can't.",
                "history": q.history,
            },
            classical={
                "deterministic_value_a_run": c.value(),
                "sample_distribution": c.sample(shots=shots),
                "history": c.history,
            },
            cognitive=cog,
        )

    @staticmethod
    def custom(*, n_qubits: int, gates: List[str], shots: int = 1024) -> Dict:
        """Run an arbitrary tiny circuit.
        gates: list of strings like 'H 0', 'X 1', 'CNOT 0 1', 'RX 0 1.5708'
        """
        if not 1 <= n_qubits <= 4:
            raise ValueError("n_qubits 1..4")
        from .quantum_lane import Gates
        q = QuantumLane(n_qubits)
        applied = []
        for spec in gates:
            tokens = spec.strip().split()
            op = tokens[0].upper()
            if op in ("H", "X", "Y", "Z", "S", "T"):
                target = int(tokens[1])
                q.apply(getattr(Gates, op), target)
                applied.append(spec)
            elif op == "CNOT":
                q.cnot(int(tokens[1]), int(tokens[2]))
                applied.append(spec)
            elif op in ("RX", "RY", "RZ"):
                target = int(tokens[1]); theta = float(tokens[2])
                q.apply(getattr(Gates, op.lower())(theta), target)
                applied.append(spec)
            else:
                raise ValueError(f"unknown gate token: {spec!r}")
        c = ClassicalLane(n_qubits)
        cog = CognitiveLane().consult(f"custom circuit on {n_qubits} qubits: {applied}")
        return TriadQuery._format(
            question=f"Custom circuit · {applied}",
            quantum={
                "state": q.state_str(),
                "probabilities": q.probabilities(),
                "measurement_counts": q.measure(shots=shots),
                "history": q.history,
            },
            classical={
                "deterministic_baseline": c.value(),
                "note": "classical lane is trivially |0...0> for the baseline; vary it via set/flip",
            },
            cognitive=cog,
        )

    @staticmethod
    def _format(*, question: str, quantum: Dict, classical: Dict, cognitive: Dict) -> Dict:
        payload = {
            "envelope": envelope(),
            "question": question,
            "lanes": {
                "quantum":   quantum,
                "classical": classical,
                "cognitive": cognitive,
            },
            "divergence_notes": _divergence_notes(quantum, classical, cognitive),
        }
        _append_log(payload)
        return payload


def _divergence_notes(qm: Dict, cl: Dict, cog: Dict) -> List[str]:
    notes: List[str] = []
    q_probs = qm.get("probabilities", {})
    c_dist = cl.get("sample_distribution", {})
    # If the quantum distribution has more nonzero outcomes than the classical
    # one, that's a sign of superposition/entanglement structure beyond LHV
    q_nonzero = sum(1 for p in q_probs.values() if p > 1e-6)
    c_nonzero = len(c_dist)
    if q_nonzero > c_nonzero:
        notes.append(f"quantum support ({q_nonzero}) > classical support ({c_nonzero}) — superposition signature")
    # If quantum has off-diagonal expectation but classical doesn't sample those
    if "expectation_XX" in qm and abs(qm["expectation_XX"]) > 0.01:
        notes.append(f"quantum <XX>={qm['expectation_XX']:.2f} — coherence the LHV imitation cannot reproduce")
    if cog.get("would_refuse"):
        notes.append(f"cognitive: F47 would refuse this question shape — {cog.get('matched_via')}")
    if cog.get("aphorism"):
        notes.append(f"cognitive aphorism: \"{cog['aphorism']['text']}\"")
    return notes or ["no notable divergence — three lanes broadly agree"]


def _append_log(payload: Dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        # Trim measurement_counts to avoid huge log entries
        light = json.loads(json.dumps(payload, default=str))
        try:
            light["lanes"]["quantum"]["measurement_counts"] = dict(
                list(light["lanes"]["quantum"]["measurement_counts"].items())[:8]
            )
        except Exception:
            pass
        f.write(json.dumps(light) + "\n")


def triad_ask(experiment: str = "bell", shots: int = 1024) -> Dict:
    """Convenience: triad_ask('bell') / 'ghz' / 'coin'."""
    e = experiment.lower()
    if e in ("bell", "bell_pair", "epr"): return TriadQuery.bell_state_query(shots=shots)
    if e in ("ghz",  "ghz3"):             return TriadQuery.ghz_query(shots=shots)
    if e in ("coin", "h", "hadamard"):    return TriadQuery.coin_query(shots=shots)
    raise ValueError(f"unknown experiment: {experiment!r}")
