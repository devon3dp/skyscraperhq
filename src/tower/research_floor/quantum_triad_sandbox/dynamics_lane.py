"""Read-only adapter exposing the existing open-system dynamics engineering."""
from __future__ import annotations

from typing import Dict, List


def dynamics_study(experiment: str = "bell", noise_levels: List[float] | None = None) -> Dict:
    from src.tower.research_floor.quantum_environment.decoherence_study import (
        bell_decay_study,
        chsh_under_noise_study,
        grover_under_noise_study,
    )

    name = experiment.lower()
    if name in ("bell", "bell_decay"):
        result = bell_decay_study(noise_levels)
    elif name in ("chsh", "chsh_noise"):
        result = chsh_under_noise_study(noise_levels)
    elif name in ("grover", "grover_noise"):
        result = grover_under_noise_study(noise_levels=noise_levels)
    else:
        raise ValueError(f"unknown dynamics experiment: {experiment!r}")
    return {
        "advisory_only": True,
        "execution_allowed": False,
        "engine": "quantum_environment open-system dynamics",
        "experiment": name,
        "result": result,
    }
