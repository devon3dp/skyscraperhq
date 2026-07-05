#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 41 OANDA Trading Floor

V1 capabilities:
- OANDA practice status.
- Account/pricing snapshot if credentials exist.
- Local-only commentary through the existing kernel chat/local model layer.
- Paper/simulation only.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

from tower.oanda_gateway import OANDAGateway

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return fallback


class OANDATradingFloor:
    def __init__(self):
        self.gateway = OANDAGateway()

    def dashboard(self):
        status = self.gateway.status()
        latest = load_json(REG / "oanda_trading_floor_latest_snapshot.json", {})

        return {
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "status": "healthy" if status.get("ready_for_account_read") else "waiting_for_credentials",
            "mode": "practice_read_only_simulation",
            "environment": "practice",
            "local_model_commentary_enabled": True,
            "account_ready": status.get("ready_for_account_read"),
            "pricing_ready": status.get("ready_for_pricing_read"),
            "paper_trading_enabled": True,
            "live_trading_enabled": False,
            "order_execution_enabled": False,
            "practice_order_execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "openclaw_execution_enabled": False,
            "autonomous_dispatch_enabled": False,
            "latest_snapshot_ts": latest.get("snapshot_ts"),
            "latest_errors": latest.get("errors", []),
            "updated_ts": datetime.now(timezone.utc).isoformat()
        }

    def snapshot(self, instruments=None):
        return self.gateway.snapshot(instruments)


def dashboard():
    return OANDATradingFloor().dashboard()


if __name__ == "__main__":
    print(json.dumps(dashboard(), indent=2))
