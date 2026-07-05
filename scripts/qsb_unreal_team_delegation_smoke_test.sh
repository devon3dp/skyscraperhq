#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] team delegation board JSON exists"
[[ -f data/registries/qsb_unreal_team_delegation_board.json ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] team delegation MD exists"
[[ -f data/logs/qsb_unreal_team_delegation_board.md ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] core members have role+status (claude/gpt_openai/deepseek/wren_local_qwen3.5_9b/hermes_local_hermes3_8b)"
jq -e '[.members.claude, .members.gpt_openai, .members.deepseek, .members.wren_local_qwen3_5_9b, .members.hermes_local_hermes3_8b]
       | map(. != null and .role != null and .status != null)
       | all' data/registries/qsb_unreal_team_delegation_board.json >/dev/null 2>&1 || {
         # try the dotted key variant (jq uses _ unless we look the key up by index)
         jq -e '.members
            | (has("claude") and has("gpt_openai") and has("deepseek") and has("wren_local_qwen3.5_9b") and has("hermes_local_hermes3_8b"))
            and (.claude.role and .claude.status)
            and (.gpt_openai.role and .gpt_openai.status)
            and (.deepseek.role and .deepseek.status)
            and (.["wren_local_qwen3.5_9b"].role and .["wren_local_qwen3.5_9b"].status)
            and (.["hermes_local_hermes3_8b"].role and .["hermes_local_hermes3_8b"].status)' \
            data/registries/qsb_unreal_team_delegation_board.json >/dev/null 2>&1 || { echo " FAIL"; fails=$((fails+1)); }
       }
echo "result: fails=$fails"
exit $fails
