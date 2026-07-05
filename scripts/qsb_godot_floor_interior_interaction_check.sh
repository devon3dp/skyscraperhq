#!/usr/bin/env bash
# qsb_godot_floor_interior_interaction_check.sh — simulate enter/back cycles
# for F55, F41, F35, F01 by writing JSONL events into a per-floor probe file.
# Cannot actually drive Godot from headless; this is a *symbolic* check that
# validates the registry entries are loadable for each target floor.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
REG="${ROOT}/data/registries/qsb_floor_interior_master_registry.json"
OUT="${ROOT}/data/registries/qsb_floor_interior_interaction_check.json"
MD="${ROOT}/data/logs/qsb_floor_interior_interaction_check.md"
mkdir -p "$(dirname "${MD}")"

python3 - <<'PY' "$REG" "$OUT" "$MD"
import json, os, sys, datetime
reg, out, md = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(reg):
    sys.exit(2)
d = json.load(open(reg))
floors_by_id = {f["floor_id"]: f for f in d["floors"]}

targets = ["F55", "F41", "F35", "F01"]
results = []
all_ok = True
for fid in targets:
    entry = floors_by_id.get(fid)
    ok = entry is not None and entry.get("interior_status") == "implemented" \
         and len(entry.get("rooms", [])) > 0 and entry.get("worker_count", 0) > 0
    if not ok: all_ok = False
    results.append({
        "floor_id": fid,
        "ok": ok,
        "template": entry.get("template") if entry else None,
        "rooms": len(entry.get("rooms", [])) if entry else 0,
        "workers": entry.get("worker_count") if entry else 0,
        "click_route": entry.get("click_route") if entry else None,
        "simulated_enter": "ok" if ok else "fail",
        "simulated_back": "ok" if ok else "fail",
    })

ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
json.dump({
    "ok": all_ok,
    "kind": "qsb_floor_interior_interaction_check",
    "ts": ts,
    "tested_floors": targets,
    "results": results,
    "note": "Symbolic — validates registry loadability + per-target completeness. Visual confirmation requires operator interaction."
}, open(out, "w"), indent=2)

with open(md, "w") as f:
    f.write(f"# Floor interior interaction check — {ts}\n\n")
    f.write(f"Tested floors: {', '.join(targets)}\n\n")
    f.write("| Floor | OK | Template | Rooms | Workers | Enter | Back |\n")
    f.write("|---|---|---|---|---|---|---|\n")
    for r in results:
        f.write("| {floor_id} | {ok} | {template} | {rooms} | {workers} | {simulated_enter} | {simulated_back} |\n".format(**r))
print(f"interaction check ok={all_ok}")
sys.exit(0 if all_ok else 1)
PY
