"""FloorToMindMap — Layer · Maps floors to cognitive layers.

The skyscraper has 53 physical floors. The Kernel has 20 cognitive
modules. Operators frequently ask "which floor does Reflection live
on?" or "which cognitive function does Floor 25 trigger?" — this is the
authoritative lookup.

Mapping is curated, not auto-discovered (changes rarely; needs human
judgement to keep accurate).
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import write_registry, now


# Authoritative mapping. Update when floors/modules shift.
FLOOR_TO_COGNITIVE: Dict[str, List[str]] = {
    # Operations / dashboard floors
    "floor_01_lobby":               ["perception"],
    "floor_02_dashboard":           ["perception", "attention", "thought_trace"],
    "floor_03_kernel_chat":         ["working_memory", "identity_gate", "self_model"],

    # Trading floors
    "floor_41_oanda_practice":      ["perception", "reasoning", "uncertainty"],
    "floor_42_binance_testnet":     ["perception", "uncertainty"],
    "floor_43_stocks_paper":        ["perception", "uncertainty"],

    # Worker / OpenClaw / orchestration
    "floor_25_worker_recruit":      ["worker_exchange", "goals", "action_proposal"],
    "floor_30_openclaw_routing":    ["openclaw_supervisor", "attention"],

    # ML/RL & research
    "floor_50_ml_rl_lab":           ["ml_rl_advisory", "learning"],
    "floor_51_research":            ["curiosity", "long_term_memory"],

    # Reflection / meta floors
    "floor_52_reflection":          ["reflection", "lesson_to_belief", "contradiction"],
    "floor_53_penthouse":           ["upgrade_assimilation", "self_model"],

    # Vacant / expansion-ready (sealed for QSB Kernel 4.5)
    "floor_44_expansion_a":         [],
    "floor_45_expansion_b":         [],
}


COGNITIVE_TO_FLOORS: Dict[str, List[str]] = {}
for _floor, _layers in FLOOR_TO_COGNITIVE.items():
    for _l in _layers:
        COGNITIVE_TO_FLOORS.setdefault(_l, []).append(_floor)


@dataclass
class FloorMindLink:
    floor: str
    cognitive_layers: List[str] = field(default_factory=list)
    sealed: bool = False
    notes: str = ""


class FloorToMindMap:
    def floor_to_layers(self, floor: str) -> List[str]:
        return list(FLOOR_TO_COGNITIVE.get(floor, []))

    def layer_to_floors(self, layer: str) -> List[str]:
        return list(COGNITIVE_TO_FLOORS.get(layer, []))

    def snapshot(self) -> dict:
        links: List[FloorMindLink] = []
        for floor, layers in FLOOR_TO_COGNITIVE.items():
            sealed = "vacant" in floor or "expansion" in floor or "penthouse" in floor
            links.append(FloorMindLink(
                floor=floor, cognitive_layers=layers,
                sealed=sealed,
                notes=("penthouse reserved for QSB Kernel 4.5"
                       if "penthouse" in floor else ""),
            ))
        return {
            "ok": True, "kind": "cognitive_floor_to_mind_map",
            "generated_ts": now(),
            "floor_count": len(FLOOR_TO_COGNITIVE),
            "cognitive_layer_count": len(COGNITIVE_TO_FLOORS),
            "links": [asdict(l) for l in links],
            "cognitive_to_floors": COGNITIVE_TO_FLOORS,
        }

    def persist(self) -> None:
        write_registry("cognitive_floor_to_mind_map.json", self.snapshot())


_MAP: Optional[FloorToMindMap] = None


def floor_mind_map() -> FloorToMindMap:
    global _MAP
    if _MAP is None:
        _MAP = FloorToMindMap()
    return _MAP
