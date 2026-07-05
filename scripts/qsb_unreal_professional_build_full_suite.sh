#!/usr/bin/env bash
# qsb_unreal_professional_build_full_suite.sh — run the full smoke battery + write a suite-level JSON+MD.

set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
JSON=data/registries/qsb_unreal_professional_build_full_suite_latest.json
MD=data/logs/qsb_unreal_professional_build_full_suite_report.md
mkdir -p data/registries data/logs

run_one() {
  local name="$1"; local script="$2"; local rc=0
  if [[ -x "$script" ]]; then
    "$script" >/tmp/qsb_smoke_${name}.log 2>&1 || rc=$?
  else
    echo "SKIP missing $script" > /tmp/qsb_smoke_${name}.log
    rc=127
  fi
  echo "$name $rc"
}

results=$(
  run_one canonical scripts/qsb_detect_canonical_tower_structure.sh
  run_one visible_build scripts/qsb_unreal_visible_build_smoke_test.sh
  run_one visual_detail scripts/qsb_unreal_visual_detail_smoke_test.sh
  run_one hud scripts/qsb_unreal_hud_smoke_test.sh
  run_one team scripts/qsb_unreal_team_delegation_smoke_test.sh
  run_one dashboard scripts/qsb_dashboard_trader_status_smoke_test.sh
)

pass=$(echo "$results" | awk '$2==0' | wc -l)
fail=$(echo "$results" | awk '$2!=0' | wc -l)

jq -n --arg ts "$TS_UTC" --arg results "$results" --argjson pass $pass --argjson fail $fail '{
  ts: $ts,
  pass: $pass,
  fail: $fail,
  results: ($results | split("\n") | map(select(length>0)))
}' > "$JSON"

cat > "$MD" <<EOF
# Full Suite Smoke Report — $TS_UTC

- Pass: $pass
- Fail: $fail

\`\`\`
$results
\`\`\`

Logs per test under /tmp/qsb_smoke_*.log
EOF

cat "$JSON"
echo "wrote $JSON + $MD"
exit $fail
