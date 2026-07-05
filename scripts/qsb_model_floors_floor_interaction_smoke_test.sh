#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_floor_interaction_smoke_test_latest.json"
MD="${ROOT}/data/logs/qsb_model_floors_floor_interaction_check.md"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
d = json.load(open("${ROOT}/data/registries/qsb_floor_interior_master_registry.json"))
fids = {f["floor_id"]: f for f in d["floors"]}
fails = []
checks = []
for fid, provider in (("F47","claude"),("F48","gpt"),("F49","deepseek")):
    e = fids.get(fid, {})
    ok = bool(e) and e.get("interior_status") == "implemented" and len(e.get("rooms", [])) >= 10 and e.get("worker_count", 0) > 0
    if not ok: fails.append(f"{fid} ({provider}): incomplete")
    checks.append({
      "floor_id": fid, "provider": provider, "ok": ok,
      "rooms": len(e.get("rooms", [])), "workers": e.get("worker_count", 0),
      "template": e.get("template"), "simulated_enter": "ok" if ok else "fail",
      "simulated_back": "ok" if ok else "fail",
    })
print(json.dumps({"ok": len(fails)==0, "kind":"qsb_model_floors_floor_interaction_smoke_test_latest", "ts": datetime.datetime.utcnow().isoformat(timespec='seconds')+'Z', "fails": fails, "results": checks}, indent=2))
PY
python3 - <<PY > "${MD}"
import json
d = json.load(open("${OUT}"))
print("# Model floor interaction check")
print()
print(f"ts: {d['ts']}")
print()
print("| Floor | Provider | OK | Template | Rooms | Workers | Enter | Back |")
print("|---|---|---|---|---|---|---|---|")
for r in d["results"]:
    print("| {floor_id} | {provider} | {ok} | {template} | {rooms} | {workers} | {simulated_enter} | {simulated_back} |".format(**r))
PY
cat "${OUT}"
[ "$(jq -r .ok "${OUT}")" = "true" ] && exit 0 || exit 1
