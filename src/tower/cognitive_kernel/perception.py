"""Perception — Layer 1 · Registry mtime watcher + JSONL tailer.

Detects what *just changed* in the QSB world. Emits typed events to
the orchestrator's bus.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
import json
import time

from . import REG, ROOT, COG_REG, write_registry, append_log


@dataclass
class PerceptionEvent:
    kind: str           # "registry_changed" | "log_appended" | "registry_added"
    source: str         # path relative to ROOT
    ts: float           # epoch
    payload: dict = field(default_factory=dict)
    novelty: float = 0.5
    urgency: float = 0.3


class Perception:
    """Polls a watched set of registries and logs for changes.

    This is NOT a true inotify subscription; it's a polling sensor.
    Cheap, robust, no extra deps. The orchestrator calls .tick() each
    cycle.
    """

    DEFAULT_WATCH_GLOBS = (
        "qsb_floor41_oanda_pnl.json",
        "qsb_lift_scene_state.json",
        "qsb_openclaw_route.json",
        "qsb_openclaw_tickets.json",
        "eqsb_guardian_state.json",
        "eqsb_cadence_state.json",
        "qsb_worker_scene_state.json",
        "qsb_3d_skyscraper_state.json",
        "eqsb_last_claude_change_summary.json",
        "qsb_ml_rl_lab_status.json",
        "qsb_native_cockpit_completion_score_v1.json",
        "qsb_godot_visual_score.json",
    )

    DEFAULT_LOG_TAILS = (
        "eqsb_phase_history.jsonl",
        "eqsb_claude_changes.jsonl",
        "eqsb_kernel_events.jsonl",
        "qsb_floor41_oanda_trade_ledger.jsonl",
    )

    def __init__(self):
        self._last_mtimes: Dict[str, float] = {}
        self._last_log_sizes: Dict[str, int] = {}

    def tick(self) -> List[PerceptionEvent]:
        events: List[PerceptionEvent] = []
        # Registry mtime watch
        for name in self.DEFAULT_WATCH_GLOBS:
            p = REG / name
            if not p.exists():
                continue
            mtime = p.stat().st_mtime
            prev = self._last_mtimes.get(name)
            if prev is None:
                self._last_mtimes[name] = mtime
                continue  # don't emit on first observation
            if mtime > prev:
                self._last_mtimes[name] = mtime
                # Try to read the new value
                payload = {}
                try:
                    payload = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    pass
                events.append(PerceptionEvent(
                    kind="registry_changed",
                    source=str(p.relative_to(ROOT)),
                    ts=mtime,
                    payload=payload,
                    novelty=0.6,
                    urgency=self._urgency_for(name),
                ))
        # Log tail watch
        for name in self.DEFAULT_LOG_TAILS:
            p = ROOT / "data/logs" / name
            if not p.exists():
                continue
            size = p.stat().st_size
            prev = self._last_log_sizes.get(name)
            if prev is None:
                self._last_log_sizes[name] = size
                continue
            if size > prev:
                self._last_log_sizes[name] = size
                events.append(PerceptionEvent(
                    kind="log_appended",
                    source=str(p.relative_to(ROOT)),
                    ts=p.stat().st_mtime,
                    payload={"bytes_added": size - prev},
                    novelty=0.45,
                    urgency=0.25,
                ))
        if events:
            append_log("perception.jsonl",
                       {"event_count": len(events),
                        "sources": [e.source for e in events]})
        return events

    @staticmethod
    def _urgency_for(name: str) -> float:
        if "guardian" in name: return 0.95
        if "openclaw" in name: return 0.75
        if "pnl" in name: return 0.70
        if "scene_state" in name: return 0.40
        if "claude" in name: return 0.65
        if "cadence" in name: return 0.25
        return 0.3


_PERCEPTION: Optional[Perception] = None


def perception() -> Perception:
    global _PERCEPTION
    if _PERCEPTION is None:
        _PERCEPTION = Perception()
    return _PERCEPTION


def persist_state(events: List[PerceptionEvent]) -> None:
    write_registry("cognitive_perception_latest.json", {
        "ok": True, "kind": "cognitive_perception_latest",
        "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "event_count": len(events),
        "events": [asdict(e) for e in events],
    })
