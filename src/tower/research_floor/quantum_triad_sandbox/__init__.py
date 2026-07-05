"""F37 Quantum Triad Sandbox — three lanes, one question, three answers.

Lanes
=====
- QuantumLane    : real classical simulation of small quantum systems (≤4 qubits).
                   State vectors over C^N (N = 2**n), unitary gates, Born-rule
                   measurement. Pure numpy. Educationally correct.
- ClassicalLane  : deterministic Boolean / integer evaluation. The control case.
- CognitiveLane  : sealed-packet bridge to F47 (Claude Embassy). Reads published
                   aphorisms, refusals, open questions — surfaces a relevant
                   perspective. Never autonomous; never executes.

Safety envelope
===============
Every packet emitted from any lane carries an envelope:
    {advisory_only: True, execution_allowed: False,
     real_money_trading: False, external_provider_call: False}

The triad does not, will not, and cannot:
- call an external quantum computer or API
- modify project files
- spend money
- unlock any execution gate
"""
from .quantum_lane import QuantumLane, Gates
from .classical_lane import ClassicalLane
from .cognitive_lane import CognitiveLane
from .triad_query import TriadQuery, triad_ask
from .safety import envelope
# v13.14 — CHSH + Grover + ASCII bars
from .algorithms import chsh_test, grover_search, probability_bars

__all__ = [
    "QuantumLane", "Gates", "ClassicalLane", "CognitiveLane",
    "TriadQuery", "triad_ask", "envelope",
    "chsh_test", "grover_search", "probability_bars",
]
