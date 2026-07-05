"""Write per-floor status registries and a combined provider_status registry."""
from __future__ import annotations
import json
import os
import datetime
from typing import Any, Dict

from .model_floor_router import ModelFloorRouter

ROOT = "/vaults/nvme0/qsb_tower_v1"


class ModelFloorReporter:
    def __init__(self) -> None:
        self.router = ModelFloorRouter()

    def write_all(self) -> Dict[str, Any]:
        ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        snap = self.router.all_status()
        self._write_json(
            os.path.join(ROOT, "data/registries/qsb_model_floor_provider_status.json"),
            {
                "ok": True,
                "kind": "qsb_model_floor_provider_status",
                "ts": ts,
                "providers": snap,
            },
        )
        self._write_json(
            os.path.join(ROOT, "data/registries/qsb_claude_floor_status.json"),
            {
                "ok": True, "kind": "qsb_claude_floor_status", "ts": ts,
                "floor_id": "F47",
                "status": snap["claude"],
                "advisory_only": True,
            },
        )
        self._write_json(
            os.path.join(ROOT, "data/registries/qsb_gpt_floor_status.json"),
            {
                "ok": True, "kind": "qsb_gpt_floor_status", "ts": ts,
                "floor_id": "F48",
                "status": snap["gpt"],
                "external_call_made_this_session": False,
            },
        )
        self._write_json(
            os.path.join(ROOT, "data/registries/qsb_deepseek_floor_status.json"),
            {
                "ok": True, "kind": "qsb_deepseek_floor_status", "ts": ts,
                "floor_id": "F49",
                "status": snap["deepseek"],
                "external_call_made_this_session": False,
            },
        )
        return snap

    def _write_json(self, path: str, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


if __name__ == "__main__":
    ModelFloorReporter().write_all()
    print("reporter wrote 4 status registries")
