#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo "======================================================"
echo "  QSB Tower V1.3 — Local Model Inference Status"
echo "======================================================"
python3 - <<'PY'
from tower.local_model_inference_gateway import LocalModelInferenceGateway
import json
s = LocalModelInferenceGateway().status()
print(json.dumps(s, indent=2))
PY
echo "======================================================"
