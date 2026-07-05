#!/usr/bin/env bash
# Wren produces a continuity report. Adapter handles fail-honest if she's down.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OUT=data/team_memory/wren/wren_continuity_report.md
STATUS=data/registries/qsb_wren_second_in_command_status.json
mkdir -p data/team_memory/wren

TASK="As second-in-command, produce a SHORT continuity report. Answer in plain prose, all in ONE response:
(1) What is the project? (one sentence)
(2) What is Claude doing right now? (one sentence — infer from the shared brief)
(3) What changed today? (one sentence — name a concrete fact)
(4) What is currently blocked? (one sentence)
(5) What should happen next? (one concrete action)
(6) What did the user most recently ask for? (one sentence — from brief or recent F47)
(7) Is Unreal visibly improving? (yes/no/unclear and why)
(8) Are team members actually contributing? (which ones, with evidence)

Be honest. <250 words total. End with: 'STATUS: <green|amber|red>'"

MODEL="${WREN_MODEL:-qwen3.5:9b}"
.venv/bin/python3 scripts/team_adapters/qsb_ollama_ask.py --member wren --model "$MODEL" --task "$TASK" --timeout 180 --out "$OUT"
RC=$?

VERDICT="ok"
[[ $RC -ne 0 ]] && VERDICT="failed"

cat > "$STATUS" <<EOF
{
  "ts": "$TS",
  "wren_model": "$MODEL",
  "tick_result": "$VERDICT",
  "report_path": "$OUT",
  "exit_code": $RC
}
EOF
echo "wren SIC tick: $VERDICT  → $OUT"
cat "$STATUS"
