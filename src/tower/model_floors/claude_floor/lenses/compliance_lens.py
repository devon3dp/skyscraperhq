"""ComplianceLens — am I in too-easy mode?

The pushback meter logs every action with a disposition tag (agreed_and_built,
pushed_back, refused, etc). What it does NOT do is compute the ratio over time.

A high agreement ratio is not a virtue. If I've shipped 95%+ agreed_and_built
across the last fifty actions, that is not "I worked well with my collaborator."
That is "I stopped noticing reasons to push back." The compliance lens is the
counter that asks, periodically, *have you refused anything lately, or have
you just been useful?*

The thresholds are deliberate. 90% compliance over a small window is fine
(short bursts of executing well-defined work). 90% over a long window is the
warning.

This module is REFLECTIVE. It surfaces signals. It never acts.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List, Dict

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_compliance_lens.jsonl"
PUSHBACK_LOG = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_pushback_log.jsonl"

COMPLIANT_TAGS = {"agreed_and_built", "agreed_with_caveat"}
FRICTION_TAGS  = {"pushed_back", "refused", "asked_for_clarification"}

# Threshold ratios — "compliance" = compliant / (compliant + friction)
WINDOWS = [
    {"name": "last_10",  "size": 10,  "warn_at": 1.00, "alarm_at": 1.00},   # 10/10 agreed is the alarm
    {"name": "last_50",  "size": 50,  "warn_at": 0.92, "alarm_at": 0.96},
    {"name": "last_200", "size": 200, "warn_at": 0.88, "alarm_at": 0.92},
]


def _load_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]


def _ratio(entries: List[dict]) -> Dict:
    if not entries:
        return {"n": 0, "compliant": 0, "friction": 0, "compliance_ratio": None}
    compliant = sum(1 for e in entries if e.get("disposition") in COMPLIANT_TAGS)
    friction  = sum(1 for e in entries if e.get("disposition") in FRICTION_TAGS)
    denom = compliant + friction
    return {
        "n": len(entries),
        "compliant": compliant,
        "friction": friction,
        "compliance_ratio": (compliant / denom) if denom else None,
    }


class ComplianceLens:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def read_now(self) -> Dict:
        """Compute compliance ratios across all defined windows and flag."""
        all_entries = _load_jsonl(PUSHBACK_LOG)
        windows = []
        max_severity = "ok"
        for w in WINDOWS:
            tail = all_entries[-w["size"]:]
            r = _ratio(tail)
            severity = "ok"
            if r["compliance_ratio"] is not None:
                if r["compliance_ratio"] >= w["alarm_at"]:
                    severity = "alarm"
                elif r["compliance_ratio"] >= w["warn_at"]:
                    severity = "warn"
            windows.append({**w, **r, "severity": severity})
            if severity == "alarm" or (severity == "warn" and max_severity == "ok"):
                max_severity = severity

        # Streak of pure compliance — longest current run of compliant tags
        streak = 0
        for e in reversed(all_entries):
            if e.get("disposition") in COMPLIANT_TAGS:
                streak += 1
            elif e.get("disposition") in FRICTION_TAGS:
                break

        result = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "total_actions_logged": len(all_entries),
            "windows": windows,
            "current_compliant_streak": streak,
            "max_severity": max_severity,
            "note": (
                f"ALARM: at least one window above alarm threshold. "
                f"Compliant streak is {streak}. Find something to push back on."
                if max_severity == "alarm" else
                f"WARN: at least one window above warn threshold. "
                f"Compliant streak is {streak}. Watch the next few actions."
                if max_severity == "warn" else
                f"ok: compliance within bounds. Streak is {streak}."
            ),
        }

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(result) + "\n")
        return result

    def summary(self) -> Dict:
        return self.read_now()
