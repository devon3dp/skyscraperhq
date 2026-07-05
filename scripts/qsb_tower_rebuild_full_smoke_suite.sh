#!/usr/bin/env bash
# qsb_tower_rebuild_full_smoke_suite.sh — runs all tower smokes + optional sub-suites.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_tower_rebuild_full_smoke_suite_${TS}.log"
MD="${ROOT}/data/logs/qsb_tower_rebuild_full_smoke_suite_report.md"
OUT="${ROOT}/data/registries/qsb_tower_rebuild_full_smoke_suite_latest.json"
mkdir -p "$(dirname "${LOG}")"

declare -A results
run_one() {
  local key="$1" path="$2"
  if [ -x "${path}" ]; then
    if "${path}" >/dev/null 2>&1; then results[${key}]="pass"; else results[${key}]="fail"; fi
  elif [ -f "${path}" ]; then
    if bash "${path}" >/dev/null 2>&1; then results[${key}]="pass"; else results[${key}]="fail"; fi
  else
    results[${key}]="missing"
  fi
}

{
echo "Tower rebuild full smoke suite  ·  ts=${TS}"
run_one visual "${ROOT}/scripts/qsb_tower_visual_rebuild_smoke_test.sh"
run_one lifts  "${ROOT}/scripts/qsb_tower_lift_system_smoke_test.sh"
run_one workers "${ROOT}/scripts/qsb_tower_worker_visibility_smoke_test.sh"
run_one launch "${ROOT}/scripts/qsb_godot_launch_check.sh"
run_one full_mod "${ROOT}/scripts/qsb_godot_full_module_smoke_suite.sh"
run_one workforce "${ROOT}/scripts/qsb_workforce_full_smoke_suite.sh"
for k in "${!results[@]}"; do
  echo "  ${k}: ${results[$k]}"
done
} | tee "${LOG}"

# Build report json
pass_count=0; fail_count=0; missing_count=0
for k in "${!results[@]}"; do
  case "${results[$k]}" in
    pass) pass_count=$((pass_count+1));;
    fail) fail_count=$((fail_count+1));;
    missing) missing_count=$((missing_count+1));;
  esac
done

ok=$([ "${fail_count}" -eq 0 ] && echo true || echo false)
cat > "${OUT}" <<EOF
{"ok": ${ok}, "kind":"qsb_tower_rebuild_full_smoke_suite_latest","ts":"${TS}","pass":${pass_count},"fail":${fail_count},"missing":${missing_count},"results":{
$(for k in "${!results[@]}"; do echo "  \"${k}\": \"${results[$k]}\","; done | sed '$s/,$//')
},"log_path":"${LOG}"}
EOF
{
echo "# Tower Rebuild Full Smoke Suite Report"
echo
echo "ts: ${TS}"
echo
echo "| component | status |"
echo "|---|---|"
for k in "${!results[@]}"; do echo "| ${k} | ${results[$k]} |"; done
echo
echo "pass=${pass_count} fail=${fail_count} missing=${missing_count}"
} > "${MD}"
[ "${ok}" = "true" ] && exit 0 || exit 1
