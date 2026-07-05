#!/usr/bin/env bash
# Full proof suite.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
J=data/registries/qsb_team_proof_suite_latest.json
MD=data/logs/qsb_team_proof_suite_report.md
mkdir -p data/registries data/logs

run() {
  local name="$1"; local script="$2"; local rc=0
  if [[ -x "$script" ]]; then
    "$script" >/tmp/qsb_proof_${name}.log 2>&1 || rc=$?
  else
    rc=127
  fi
  echo "$name $rc"
}

results=$(
  run persistence    scripts/qsb_team_prove_persistence.sh
  run model_calls    scripts/qsb_team_prove_model_calls.sh
  run memory_sync    scripts/qsb_team_prove_memory_sync.sh
  run delegation     scripts/qsb_team_prove_delegation.sh
  run wren_second    scripts/qsb_team_prove_wren_second.sh
  run unreal_driver  scripts/qsb_team_prove_unreal_driver.sh
)

pass=$(echo "$results" | awk '$2==0' | wc -l)
fail=$(echo "$results" | awk '$2!=0' | wc -l)

jq -n --arg ts "$TS" --arg results "$results" --argjson pass $pass --argjson fail $fail '{
  ts: $ts, pass: $pass, fail: $fail,
  results: ($results | split("\n") | map(select(length>0)))
}' > $J

cat > $MD <<EOF
# Team Proof Suite — $TS

Pass: $pass · Fail: $fail

\`\`\`
$results
\`\`\`

Per-test logs at /tmp/qsb_proof_*.log
EOF

cat $J
exit $fail
