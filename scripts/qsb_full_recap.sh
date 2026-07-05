#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo "======================================================"
echo "  QSB Tower V1.3 — Full System Recap / Inventory"
echo "  Phase: QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1"
echo "======================================================"
python3 - <<'PY'
from tower.dashboard_render_model import build
import json
out = build()
print(json.dumps({
    "phase": "QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1",
    "counts": out["inventory"]["counts"],
    "floor_name_map_count": len(out["name_map"]["name_map"]),
    "render_model_floors": len(out["render_model"]["floors"]),
    "render_model_routes": len(out["render_model"]["routes"]),
    "highlighted_floors": out["render_model"]["highlighted_floors"],
    "airllm_chamber_advisory_only": out["inventory"]["airllm_chamber"]["advisory_only"],
    "execution_allowed": False,
    "paper_only": True,
    "not_financial_advice": True,
}, indent=2))
PY
echo "======================================================"
