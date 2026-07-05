#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_godot_scene_smoke_test_latest.json"
fail=0
for s in \
  "${PROJECT}/scenes/model_floors/ClaudeFloorInterior.tscn" \
  "${PROJECT}/scenes/model_floors/GPTFloorInterior.tscn" \
  "${PROJECT}/scenes/model_floors/DeepSeekFloorInterior.tscn" \
  "${PROJECT}/scripts/model_floors/ClaudeFloorPanel.gd" \
  "${PROJECT}/scripts/model_floors/GPTFloorPanel.gd" \
  "${PROJECT}/scripts/model_floors/DeepSeekFloorPanel.gd" \
  "${PROJECT}/scripts/model_floors/ModelFloorRouter.gd" \
  "${PROJECT}/scripts/model_floors/ModelConsolePanel.gd" \
  "${PROJECT}/scripts/model_floors/ModelProviderStatusPanel.gd" \
  "${PROJECT}/scripts/model_floors/ModelCostGuardPanel.gd" \
  "${PROJECT}/scripts/model_floors/ModelCollaborationPanel.gd"; do
  [ -f "${s}" ] || fail=$((fail+1))
done
# Master registry must include our 3 floors with new templates
python3 - <<PY || fail=$((fail+1))
import json
d = json.load(open("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_floor_interior_master_registry.json"))
fids = {f["floor_id"]: f for f in d["floors"]}
assert fids["F47"]["template"] == "ClaudeEmbassyInterior", fids["F47"]["template"]
assert fids["F48"]["template"] == "GPTEmbassyInterior", fids["F48"]["template"]
assert fids["F49"]["template"] == "DeepSeekEmbassyInterior", fids["F49"]["template"]
print("master registry templates ok")
PY
cat > "${OUT}" <<EOF
{"ok": $([ ${fail} -eq 0 ] && echo true || echo false), "kind":"qsb_model_floors_godot_scene_smoke_test_latest","ts":"${TS}","fail":${fail}}
EOF
cat "${OUT}"
[ ${fail} -eq 0 ] && exit 0 || exit 1
