#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_assignment_smoke_test_latest.json"
python3 - <<PY > "${OUT}"
import json, datetime
ROOT = "${ROOT}"
fail = 0
a = json.load(open(f"{ROOT}/data/registries/qsb_three_model_embassy_floor_assignments.json"))
m = json.load(open(f"{ROOT}/data/registries/qsb_model_floor_registry.json"))
fids_a = sorted(x["floor_id"] for x in a["assignments"])
fids_m = sorted(x["floor_id"] for x in m["floors"])
if fids_a != fids_m: fail += 1
if len(set(fids_a)) != len(fids_a): fail += 1
provs = sorted(x["provider"] for x in a["assignments"])
if provs != ["claude","deepseek","gpt"]: fail += 1
print(json.dumps({"ok": fail == 0, "kind":"qsb_model_floors_assignment_smoke_test_latest", "ts": datetime.datetime.utcnow().isoformat(timespec='seconds')+'Z', "fail": fail, "floor_ids": fids_a, "providers": provs}, indent=2))
PY
cat "${OUT}"
[ "$(jq -r .ok "${OUT}")" = "true" ] && exit 0 || exit 1
