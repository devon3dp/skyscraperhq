"""MLRLAdvisoryBrain — Layer · Bridge to the ML/RL Lab.

The lab lives at /vaults/ai/qsb_ml_rl_lab and runs offline. The Kernel
does NOT call torch / RL training from here. Instead it:

  - reads the lab's status registry (qsb_ml_rl_lab_status.json)
  - records advisory summaries (e.g., "smoke tests last pass time",
    "model checkpoint freshness")
  - proposes — but never schedules — retraining when checkpoint age
    crosses a threshold

Hard rule: training is operator-initiated.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import time

from . import append_log, write_registry, now, load, REG
from .working_memory import blackboard
from .uncertainty import uncertainty
from .action_proposal import action_proposer


@dataclass
class LabAdvisory:
    ts: float
    lab_status_present: bool
    smoke_tests_last_pass_ts: Optional[float]
    checkpoint_age_seconds: Optional[float]
    advisory_notes: List[str] = field(default_factory=list)


class MLRLAdvisoryBrain:
    CHECKPOINT_STALE_THRESHOLD_S = 7 * 24 * 3600   # 1 week

    def __init__(self):
        self._last: Optional[LabAdvisory] = None

    def observe(self) -> LabAdvisory:
        status = load(REG / "qsb_ml_rl_lab_status.json")
        notes: List[str] = []
        smoke_ts = None
        ckpt_age = None
        present = bool(status)

        if isinstance(status, dict):
            smoke_ts_raw = status.get("smoke_tests_last_pass_ts") or status.get("last_smoke_pass_ts")
            if isinstance(smoke_ts_raw, (int, float)):
                smoke_ts = float(smoke_ts_raw)
            ckpt_ts_raw = (status.get("checkpoint_last_written_ts")
                            or status.get("last_checkpoint_ts"))
            if isinstance(ckpt_ts_raw, (int, float)):
                ckpt_age = max(0.0, time.time() - float(ckpt_ts_raw))
                if ckpt_age > self.CHECKPOINT_STALE_THRESHOLD_S:
                    notes.append("checkpoint_stale_gt_1_week")
            else:
                notes.append("no_checkpoint_timestamp")
            if status.get("torch_install_ok") is False:
                notes.append("torch_install_failed")
            if status.get("torchrl_install_ok") is False:
                notes.append("torchrl_install_failed")

        adv = LabAdvisory(
            ts=time.time(), lab_status_present=present,
            smoke_tests_last_pass_ts=smoke_ts,
            checkpoint_age_seconds=ckpt_age,
            advisory_notes=notes,
        )
        self._last = adv

        # Mirror to working memory
        blackboard().write(
            key="ml_rl_lab_advisory",
            value=asdict(adv),
            source="qsb_ml_rl_lab_status.json",
            priority=0.4,
            ttl_seconds=1800,
            tags=["ml", "rl", "advisory"],
        )
        uncertainty().assert_(
            key="ml_rl_lab_status",
            statement=("ML/RL lab status registry present"
                       if present else "ML/RL lab status registry missing"),
            confidence=0.85 if present else 0.2,
            source="ml_rl_advisory",
            half_life_seconds=3600.0,
            tags=["ml", "rl"],
        )

        if "checkpoint_stale_gt_1_week" in notes:
            action_proposer().propose(
                title="ML/RL checkpoint stale (>1 week)",
                rationale=("Latest checkpoint timestamp exceeds 1 week. "
                           "Operator-initiated retraining recommended."),
                proposed_action="operator: review qsb_ml_rl_lab_status.json and trigger retraining manually",
                requires_approval_from="operator",
                confidence=0.65,
                tags=["ml", "rl", "advisory"],
            )

        append_log("ml_rl_advisory.jsonl", asdict(adv))
        return adv

    def persist(self) -> None:
        write_registry("cognitive_ml_rl_advisory.json", {
            "ok": True, "kind": "cognitive_ml_rl_advisory",
            "generated_ts": now(),
            "policy": "Advisory only. Training is operator-initiated. Kernel does not call torch.",
            "last_advisory": asdict(self._last) if self._last else None,
        })


_ADVISORY: Optional[MLRLAdvisoryBrain] = None


def ml_rl_advisory() -> MLRLAdvisoryBrain:
    global _ADVISORY
    if _ADVISORY is None:
        _ADVISORY = MLRLAdvisoryBrain()
    return _ADVISORY
