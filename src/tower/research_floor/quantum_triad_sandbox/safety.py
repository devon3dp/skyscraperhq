"""Envelope stamping — every triad packet carries the floor's safety posture."""
from __future__ import annotations
import datetime
from typing import Dict


def envelope() -> Dict:
    return {
        "advisory_only":        True,
        "execution_allowed":    False,
        "real_money_trading":   False,
        "external_provider_call": False,
        "openclaw_real_tool_execution": False,
        "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "from": "F37 Strategy Labs · Quantum Triad Sandbox",
    }
