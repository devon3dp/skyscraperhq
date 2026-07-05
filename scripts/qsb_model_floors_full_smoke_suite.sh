#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_model_floors_full_smoke_suite_${TS}.log"
MD="${ROOT}/data/logs/qsb_model_floors_full_smoke_suite_report.md"
OUT="${ROOT}/data/registries/qsb_model_floors_full_smoke_suite_latest.json"
mkdir -p "$(dirname "${LOG}")"

declare -A r
run() { local key="$1" path="$2"; if [ -x "${path}" ]; then "${path}" >/dev/null 2>&1 && r[$key]="pass" || r[$key]="fail"; else r[$key]="missing"; fi; }
{
echo "Model embassy floors · full smoke suite · ts=${TS}"
run assignment   "${ROOT}/scripts/qsb_model_floors_assignment_smoke_test.sh"
run env          "${ROOT}/scripts/qsb_model_floors_env_smoke_test.sh"
run secret       "${ROOT}/scripts/qsb_model_floors_secret_safety_smoke_test.sh"
run health       "${ROOT}/scripts/qsb_model_floors_provider_health_smoke_test.sh"
run godot        "${ROOT}/scripts/qsb_model_floors_godot_scene_smoke_test.sh"
run intent       "${ROOT}/scripts/qsb_model_floors_command_intent_smoke_test.sh"
run interaction  "${ROOT}/scripts/qsb_model_floors_floor_interaction_smoke_test.sh"
run cost         "${ROOT}/scripts/qsb_model_floors_cost_guard_smoke_test.sh"
for k in "${!r[@]}"; do echo "  ${k}: ${r[$k]}"; done
} | tee "${LOG}"

pass=0; fail=0; miss=0
for k in "${!r[@]}"; do
  case "${r[$k]}" in pass) pass=$((pass+1));; fail) fail=$((fail+1));; missing) miss=$((miss+1));; esac
done
ok=$([ "${fail}" -eq 0 ] && echo true || echo false)
cat > "${OUT}" <<EOF
{"ok": ${ok}, "kind":"qsb_model_floors_full_smoke_suite_latest","ts":"${TS}","pass":${pass},"fail":${fail},"missing":${miss},"results":{$(for k in "${!r[@]}"; do echo "  \"${k}\": \"${r[$k]}\","; done | sed '$s/,$//')},"log_path":"${LOG}"}
EOF
{
echo "# Model embassy floors · full smoke suite"; echo
echo "ts: ${TS}"; echo
echo "| component | status |"; echo "|---|---|"
for k in "${!r[@]}"; do echo "| ${k} | ${r[$k]} |"; done
echo; echo "pass=${pass} fail=${fail} missing=${miss}"
} > "${MD}"
[ "${ok}" = "true" ] && exit 0 || exit 1
