#!/usr/bin/env bash
# qsb_tower_lift_system_smoke_test.sh
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_tower_lift_system_smoke_test_${TS}.log"
OUT="${ROOT}/data/registries/qsb_tower_lift_system_smoke_test_latest.json"
mkdir -p "$(dirname "${LOG}")"
pass=0; fail=0
check() { if [ -f "$1" ]; then echo "PASS: $1"; pass=$((pass+1)); else echo "FAIL: $1"; fail=$((fail+1)); fi; }
{
echo "Tower lift smoke  ·  ts=${TS}"
check "${PROJECT}/scripts/TowerLiftSystem.gd"
check "${PROJECT}/scripts/TowerLiftCar.gd"
check "${ROOT}/data/registries/qsb_tower_lift_positions.json"
check "${ROOT}/data/registries/qsb_tower_lift_system_status.json"
# Lift count & state validation
if [ -f "${ROOT}/data/registries/qsb_tower_lift_positions.json" ]; then
  python3 - <<'PY' && pass=$((pass+5)) || fail=$((fail+1))
import json, sys
d = json.load(open("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_tower_lift_positions.json"))
lifts = d.get("lifts", [])
assert len(lifts) >= 3, f"need >=3 lifts got {len(lifts)}"
ids = [l["lift_id"] for l in lifts]
assert len(ids) == len(set(ids)), "duplicate lift_ids"
valid_states = {"idle","moving","arriving","loading","blocked"}
for l in lifts:
    assert l["state"] in valid_states, f"bad state {l['state']}"
    assert 1 <= l["current_floor"] <= 55, f"bad current_floor {l['current_floor']}"
    assert 1 <= l["target_floor"] <= 55, f"bad target_floor {l['target_floor']}"
print(f"PASS: lift validation · {len(lifts)} lifts, all states + floors valid")
PY
fi
# Selected-floor focus capability is signalled by status registry
if grep -q '"click_focus_routes_lift": true' "${ROOT}/data/registries/qsb_tower_lift_system_status.json" 2>/dev/null; then
  echo "PASS: click_focus_routes_lift=true"; pass=$((pass+1))
else
  echo "FAIL: click_focus_routes_lift missing"; fail=$((fail+1))
fi
# Event log writable
LOG_LIFTS="${ROOT}/data/logs/qsb_tower_lift_events.jsonl"
touch "${LOG_LIFTS}" 2>/dev/null && echo "PASS: lift event log writable (${LOG_LIFTS})" && pass=$((pass+1)) || (echo "FAIL: lift event log"; fail=$((fail+1)))
echo "TOTAL: pass=${pass} fail=${fail}"
} | tee "${LOG}"
cat > "${OUT}" <<EOF
{"ok": $([ "${fail}" -eq 0 ] && echo true || echo false), "kind":"qsb_tower_lift_system_smoke_test_latest","ts":"${TS}","pass":${pass},"fail":${fail},"log_path":"${LOG}"}
EOF
[ "${fail}" -eq 0 ] && exit 0 || exit 1
