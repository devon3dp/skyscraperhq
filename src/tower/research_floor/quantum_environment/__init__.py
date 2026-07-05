"""F37 Quantum Environment — open quantum systems on F37.

Where the triad sandbox simulates *closed* quantum mechanics (pure state
vectors evolve unitarily), this package simulates the *open* version: the
qubit register coupled to an environment. Real physics:
  · density matrix representation (mixed states allowed)
  · Kraus channels for amplitude damping (T1), phase damping (T2),
    depolarizing, bit-flip, phase-flip noise
  · NoisyCircuit composer: insert a channel after every gate
  · Bell-under-decoherence: watch entanglement fade
  · CHSH-under-decoherence: watch the Tsirelson bound retreat to 2

All advisory-only. No external calls. No new dependencies. Pure Python.
"""
from .density import DensityMatrix
from .channels import (
    amplitude_damping, phase_damping, depolarizing,
    bit_flip, phase_flip, identity_channel,
)
from .open_system import NoisyCircuit
from .bloch import bloch_vector, purity
from .concurrence import concurrence
from .decoherence_study import (
    bell_decay_study, chsh_under_noise_study, grover_under_noise_study,
)

__all__ = [
    "DensityMatrix",
    "amplitude_damping", "phase_damping", "depolarizing",
    "bit_flip", "phase_flip", "identity_channel",
    "NoisyCircuit",
    "bloch_vector", "purity",
    "bell_decay_study", "chsh_under_noise_study", "grover_under_noise_study",
]
