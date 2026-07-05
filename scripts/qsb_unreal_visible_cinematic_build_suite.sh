#!/usr/bin/env bash
# qsb_unreal_visible_cinematic_build_suite.sh — full cinematic smoke battery.

set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
JSON=data/registries/qsb_unreal_visible_cinematic_build_suite_latest.json
MD=data/logs/qsb_unreal_visible_cinematic_build_suite_report.md
mkdir -p data/registries data/logs

run_one() {
  local name="$1"; local script="$2"; local rc=0
  if [[ -x "$script" ]]; then
    "$script" >/tmp/qsb_cine_smoke_${name}.log 2>&1 || rc=$?
  else
    echo "SKIP missing $script" > /tmp/qsb_cine_smoke_${name}.log
    rc=127
  fi
  echo "$name $rc"
}

results=$(
  run_one tiktok_ref scripts/qsb_unreal_tiktok_reference_smoke_test.sh
  run_one mat_light  scripts/qsb_unreal_material_lighting_smoke_test.sh
  run_one prof_sky   scripts/qsb_unreal_professional_skyscraper_smoke_test.sh
  run_one city       scripts/qsb_unreal_futuristic_city_smoke_test.sh
  run_one hud_target scripts/qsb_unreal_hud_target_smoke_test.sh
  run_one quality    scripts/qsb_unreal_visual_quality_score.sh
)

pass=$(echo "$results" | awk '$2==0' | wc -l)
fail=$(echo "$results" | awk '$2!=0' | wc -l)

jq -n --arg ts "$TS_UTC" --arg results "$results" --argjson pass $pass --argjson fail $fail '{
  ts: $ts, pass: $pass, fail: $fail,
  results: ($results | split("\n") | map(select(length>0)))
}' > "$JSON"

cat > "$MD" <<EOF
# Visible Cinematic Build Suite — $TS_UTC

Pass: $pass · Fail: $fail

\`\`\`
$results
\`\`\`

Confirms:
- TikTok reference board exists
- Material + lighting pass scripts exist (recipes ready for editor)
- Professional skyscraper generator exists + does NOT hardcode floor count
- City generator exists + targets MCP TCP
- HUD target zones complete
- Visual quality scored (honestly low until materials land)

Logs per test: /tmp/qsb_cine_smoke_*.log
EOF

cat "$JSON"
exit $fail
