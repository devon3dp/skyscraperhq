"""ClassicalLane — deterministic Boolean / integer evaluation.

The control case. Same question, no superposition, no entanglement,
no measurement uncertainty. Useful as the baseline against which the
quantum and cognitive lanes are compared.
"""
from __future__ import annotations
import random
from typing import Any, Dict, List, Optional


class ClassicalLane:
    def __init__(self, n_bits: int = 3, seed: Optional[int] = None) -> None:
        self.n = n_bits
        self.rng = random.Random(seed)
        self.state: List[int] = [0] * n_bits
        self.history: List[str] = []

    def set(self, q: int, value: int) -> "ClassicalLane":
        self.state[q] = 1 if value else 0
        self.history.append(f"set(q={q}, {value})")
        return self

    def flip(self, q: int) -> "ClassicalLane":
        self.state[q] ^= 1
        self.history.append(f"flip(q={q})")
        return self

    def xor(self, control: int, target: int) -> "ClassicalLane":
        self.state[target] ^= self.state[control]
        self.history.append(f"xor(c={control}, t={target})")
        return self

    def coin(self, q: int) -> "ClassicalLane":
        self.state[q] = self.rng.randint(0, 1)
        self.history.append(f"coin(q={q})")
        return self

    def value(self) -> str:
        return "".join(str(b) for b in self.state)

    def sample(self, shots: int = 1024) -> Dict[str, int]:
        """For a deterministic state, sample is trivially the state with prob 1."""
        return {self.value(): shots}

    @staticmethod
    def deterministic_bell_analog() -> "ClassicalLane":
        """The closest classical analog of a Bell pair: a shared random bit.
        Bit 0 is random; bit 1 is forced equal to bit 0. Probabilities match
        {00: 0.5, 11: 0.5} just like |Φ+> — BUT no entanglement, no nonlocal
        correlations: this is the LHV (local hidden variable) imitation."""
        c = ClassicalLane(2)
        c.coin(0)
        c.state[1] = c.state[0]
        c.history.append("bell_analog (LHV imitation)")
        return c

    @staticmethod
    def deterministic_ghz_analog() -> "ClassicalLane":
        c = ClassicalLane(3)
        c.coin(0)
        c.state[1] = c.state[0]
        c.state[2] = c.state[0]
        c.history.append("ghz_analog (LHV imitation)")
        return c

    @staticmethod
    def classical_coin() -> "ClassicalLane":
        c = ClassicalLane(1)
        c.coin(0)
        return c
