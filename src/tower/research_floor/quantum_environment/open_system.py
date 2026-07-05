"""NoisyCircuit — compose unitary gates with noise channels.

Insert a noise channel after every gate to model environment coupling.
Tracks purity, entropy, Bloch vectors across time to make decoherence visible.
"""
from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple

from .density import DensityMatrix
from .channels import identity_channel


GateSpec = Tuple[str, ...]   # ("H", q) or ("CNOT", c, t)


class NoisyCircuit:
    def __init__(self, n_qubits: int,
                 *, channel_factory: Optional[Callable[[], List]] = None,
                 channel_label: str = "noise") -> None:
        self.dm = DensityMatrix(n_qubits)
        self.n = n_qubits
        self.gates: List[GateSpec] = []
        self.channel_factory = channel_factory
        self.channel_label = channel_label
        self.history: List[Dict] = []

    def add(self, *spec: str) -> "NoisyCircuit":
        self.gates.append(spec)
        return self

    def run(self, *, snapshot_every: int = 1) -> List[Dict]:
        """Apply each gate then the noise channel on every active qubit.
        Returns a snapshot list with purity, entropy, Bloch coords (first
        qubit reduced), and a sample of probabilities."""
        from src.tower.research_floor.quantum_triad_sandbox.quantum_lane import Gates
        from .bloch import bloch_vector
        snapshots: List[Dict] = []
        for step, gate in enumerate(self.gates):
            op = gate[0].upper()
            if op == "H":      self.dm.apply_unitary_1q(Gates.H, int(gate[1]))
            elif op == "X":    self.dm.apply_unitary_1q(Gates.X, int(gate[1]))
            elif op == "Y":    self.dm.apply_unitary_1q(Gates.Y, int(gate[1]))
            elif op == "Z":    self.dm.apply_unitary_1q(Gates.Z, int(gate[1]))
            elif op == "S":    self.dm.apply_unitary_1q(Gates.S, int(gate[1]))
            elif op == "T":    self.dm.apply_unitary_1q(Gates.T, int(gate[1]))
            elif op == "RY":   self.dm.apply_unitary_1q(Gates.ry(float(gate[2])), int(gate[1]))
            elif op == "RX":   self.dm.apply_unitary_1q(Gates.rx(float(gate[2])), int(gate[1]))
            elif op == "RZ":   self.dm.apply_unitary_1q(Gates.rz(float(gate[2])), int(gate[1]))
            elif op == "CNOT": self.dm.apply_cnot(int(gate[1]), int(gate[2]))
            # v13.16: arbitrary basis-state phase flips — enables real Grover oracle
            elif op == "PHASE_FLIP":
                idx = int(gate[1])
                if not 0 <= idx < 2 ** self.n:
                    raise ValueError(f"PHASE_FLIP index {idx} out of range")
                # Flip sign of row idx and column idx of ρ
                for k in range(2 ** self.n):
                    self.dm.rho[idx][k] = -self.dm.rho[idx][k]
                for k in range(2 ** self.n):
                    self.dm.rho[k][idx] = -self.dm.rho[k][idx]
                self.dm.history.append(f"PHASE_FLIP({idx:0{self.n}b})")
            # v13.16: Grover diffusion — reflect about |0...0>, sign-flip every non-zero state
            elif op == "REFLECT_ABOUT_ZERO":
                for k in range(1, 2 ** self.n):
                    for c in range(2 ** self.n):
                        self.dm.rho[k][c] = -self.dm.rho[k][c]
                    for r in range(2 ** self.n):
                        self.dm.rho[r][k] = -self.dm.rho[r][k]
                self.dm.history.append("REFLECT_ABOUT_ZERO")
            else: raise ValueError(f"unknown gate: {gate}")

            if self.channel_factory:
                kraus = self.channel_factory()
                for q in range(self.n):
                    self.dm.apply_kraus_1q(kraus, q, label=self.channel_label)

            if step % snapshot_every == 0:
                snap = {
                    "step": step,
                    "gate": gate,
                    "purity": self.dm.purity(),
                    "trace": float(self.dm.trace().real),
                    "bloch_q0": bloch_vector(self.dm, qubit=0),
                }
                if self.n >= 2:
                    snap["entropy_q0_subsystem"] = self.dm.partial_trace([0]).von_neumann_entropy()
                snapshots.append(snap)
        return snapshots

    def measure_observable(self, observable: str) -> float:
        return self.dm.expectation(observable)

    def probabilities(self) -> Dict[str, float]:
        return self.dm.probabilities()
