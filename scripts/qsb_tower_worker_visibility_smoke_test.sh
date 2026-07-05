#!/usr/bin/env bash
# qsb_tower_worker_visibility_smoke_test.sh
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_tower_worker_visibility_smoke_test_${TS}.log"
OUT="${ROOT}/data/registries/qsb_tower_worker_visibility_smoke_test_latest.json"
mkdir -p "$(dirname "${LOG}")"
pass=0; fail=0
check() { if [ -f "$1" ]; then echo "PASS: $1"; pass=$((pass+1)); else echo "FAIL: $1"; fail=$((fail+1)); fi; }
{
echo "Tower worker visibility smoke  ·  ts=${TS}"
check "${PROJECT}/scripts/TowerWorkerVisualizer.gd"
check "${PROJECT}/scripts/TowerWorkerActivityAnimator.gd"
check "${ROOT}/data/registries/qsb_tower_worker_density_map.json"
check "${ROOT}/data/registries/qsb_tower_worker_visibility_status.json"
check "${ROOT}/data/registries/qsb_tower_worker_animation_status.json"
# Population source — check any of the registries
for p in \
  data/registries/qsb_workforce_population_count_latest.json \
  data/registries/qsb_floor_worker_presence_map.json \
  data/registries/qsb_floor_interior_master_registry.json
do
  if [ -f "${ROOT}/${p}" ]; then echo "PASS: population source ${p}"; pass=$((pass+1)); break; fi
done
# Role categories present in status
python3 - <<'PY' && pass=$((pass+1)) || fail=$((fail+1))
import json
d = json.load(open("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_tower_worker_visibility_status.json"))
roles = set(d.get("roles_represented", []))
required = {"manager","worker","watcher","seer","overseer","trainer","butler","concierge","clerk","analyst"}
missing = required - roles
assert not missing, f"missing roles: {missing}"
print("PASS: all required roles represented")
PY
# LOD/perf policy
if grep -q '"performance_cap"' "${ROOT}/data/registries/qsb_tower_worker_visibility_status.json" 2>/dev/null; then
  echo "PASS: performance_cap present"; pass=$((pass+1))
else
  echo "FAIL: performance_cap missing"; fail=$((fail+1))
fi
echo "TOTAL: pass=${pass} fail=${fail}"
} | tee "${LOG}"
cat > "${OUT}" <<EOF
{"ok": $([ "${fail}" -eq 0 ] && echo true || echo false), "kind":"qsb_tower_worker_visibility_smoke_test_latest","ts":"${TS}","pass":${pass},"fail":${fail},"log_path":"${LOG}"}
EOF
[ "${fail}" -eq 0 ] && exit 0 || exit 1
