#!/usr/bin/env bash
# qsb_floor_interior_coverage_audit.sh — verify F01..F55 coverage.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_floor_interior_coverage_audit_${TS}.log"
OUT="${ROOT}/data/registries/qsb_floor_interior_coverage_audit_latest.json"
REG="${ROOT}/data/registries/qsb_floor_interior_master_registry.json"
mkdir -p "$(dirname "${LOG}")"

python3 - <<'PY' "$REG" "$OUT" "$LOG" "$TS"
import json, os, sys, datetime
reg_path, out_path, log_path, ts = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

def fail(reason, code=1):
    json.dump({"ok": False, "kind": "qsb_floor_interior_coverage_audit_latest",
               "ts": ts, "reason": reason}, open(out_path, "w"), indent=2)
    print("FAIL:", reason); sys.exit(code)

if not os.path.exists(reg_path):
    fail("master registry missing")
d = json.load(open(reg_path))
floors = d.get("floors", [])
fail_count, ok_count = 0, 0
issues = []

required_ids = {f"F{i:02d}" for i in range(1, 56)}
present_ids = {f["floor_id"] for f in floors}
missing = required_ids - present_ids
if missing:
    issues.append(f"missing floor ids: {sorted(missing)[:5]}")
    fail_count += len(missing)

key_specialized = {
    "F55": "KernelPenthouseInterior",
    "F41": "TradingFloorInterior",
    "F42": "TradingFloorInterior",
    "F35": "HardwareObservatoryInterior",
    "F50": "MLRLClassroomInterior",
    "F30": "SecurityGuardianInterior",
    "F28": "SecurityGuardianInterior",
}
spec_check = {f["floor_id"]: f for f in floors}
for fid, expected in key_specialized.items():
    if fid not in spec_check:
        issues.append(f"{fid} missing"); fail_count += 1
        continue
    actual = spec_check[fid].get("template", "")
    if actual != expected:
        issues.append(f"{fid} expected template {expected}, got {actual}")
        fail_count += 1

# Per-floor checks
for entry in floors:
    fid = entry["floor_id"]
    if not entry.get("rooms"):
        issues.append(f"{fid} has zero rooms"); fail_count += 1
    elif "Penthouse" in entry.get("floor_name", "") and len(entry["rooms"]) < 10:
        issues.append(f"{fid} (penthouse) has <10 rooms"); fail_count += 1
    elif entry["template"] in {"TradingFloorInterior","MLRLClassroomInterior","BankingCommerceInterior",
                                 "SecurityGuardianInterior","HardwareObservatoryInterior"} and len(entry["rooms"]) < 8:
        issues.append(f"{fid} special template has <8 rooms"); fail_count += 1
    elif entry["template"] == "GenericFloorInterior" and len(entry["rooms"]) < 5:
        issues.append(f"{fid} generic has <5 rooms"); fail_count += 1
    if not entry.get("template"):
        issues.append(f"{fid} no template"); fail_count += 1
    if not entry.get("click_route"):
        issues.append(f"{fid} no click_route"); fail_count += 1
    if entry.get("worker_count", 0) <= 0:
        issues.append(f"{fid} no workers"); fail_count += 1
    if entry.get("interior_status") == "implemented" and not entry.get("rooms"):
        issues.append(f"{fid} marked implemented but no rooms"); fail_count += 1
    if entry.get("interior_status") == "implemented":
        ok_count += 1

result = {
    "ok": fail_count == 0,
    "kind": "qsb_floor_interior_coverage_audit_latest",
    "ts": ts,
    "floor_count_required": 55,
    "floor_count_present": len(floors),
    "ok_count": ok_count,
    "fail_count": fail_count,
    "issues": issues,
}
json.dump(result, open(out_path, "w"), indent=2)
with open(log_path, "w") as f:
    f.write(f"coverage audit · ts={ts}\n")
    f.write(f"floors present: {len(floors)} / 55\n")
    f.write(f"ok: {ok_count} · fail: {fail_count}\n")
    for i in issues[:20]:
        f.write("  ! " + i + "\n")
print(f"coverage audit · ok={result['ok']} · fail_count={fail_count}")
sys.exit(0 if result["ok"] else 1)
PY
