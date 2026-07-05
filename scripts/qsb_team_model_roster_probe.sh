#!/usr/bin/env bash
# qsb_team_model_roster_probe.sh — detect available team members (real check, no faking)
set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OUT_JSON=data/registries/qsb_team_model_roster_latest.json
OUT_MD=data/logs/qsb_team_model_roster_report.md
mkdir -p data/registries data/logs

ollama_ok=no
ollama_list=""
if command -v ollama >/dev/null 2>&1; then
  ollama_ok=yes
  ollama_list=$(ollama list 2>/dev/null | tail -n +2)
fi

find_model() {
  echo "$ollama_list" | awk -v pat="$1" 'tolower($1) ~ pat {print $1; exit}'
}
WREN_ID=$(find_model "wren|qwen")
HERMES_ID=$(find_model "hermes")
IQUEST_ID=$(find_model "iquest|coder")
LLAVA_ID=$(find_model "llava|vision")
DEEPSEEK_ID=$(find_model "deepseek")

claude_cli=$(command -v claude >/dev/null 2>&1 && echo yes || echo no)
ue_editor=/vaults/nvme0/UnrealEngine/Engine/Binaries/Linux/UnrealEditor
ue_avail=$( [[ -x "$ue_editor" ]] && echo yes || echo no )
ue_project=/vaults/nvme0/qsb_unreal_skyscraper/QSB_Skyscraper.uproject
ue_project_avail=$( [[ -f "$ue_project" ]] && echo yes || echo no )
mem_dir_ok=$( [[ -d data/team_memory ]] && echo yes || echo no )

# Wren via Ollama directly?
wren_curl_ok=no
if curl -s --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  wren_curl_ok=yes
fi

cat > "$OUT_JSON" <<EOF
{
  "ts": "$TS",
  "ollama_available": "$ollama_ok",
  "ollama_endpoint_reachable": "$wren_curl_ok",
  "wren_local_model_id": "${WREN_ID:-NOT_AVAILABLE}",
  "hermes_local_model_id": "${HERMES_ID:-NOT_AVAILABLE}",
  "iquest_coder_local_model_id": "${IQUEST_ID:-NOT_AVAILABLE}",
  "llava_vision_model_id": "${LLAVA_ID:-NOT_AVAILABLE}",
  "deepseek_local_model_id": "${DEEPSEEK_ID:-NOT_AVAILABLE}",
  "claude_cli_available": "$claude_cli",
  "claude_active_as_execution_captain": true,
  "unreal_editor_binary_available": "$ue_avail",
  "unreal_editor_path": "$ue_editor",
  "unreal_project_available": "$ue_project_avail",
  "unreal_project_path": "$ue_project",
  "team_memory_dir_exists": "$mem_dir_ok",
  "providers_advisory_only": ["openai", "deepseek"]
}
EOF

cat > "$OUT_MD" <<EOF
# QSB Team Model Roster — $TS

- **Claude CLI active** as execution captain
- **Wren local model:** ${WREN_ID:-NOT AVAILABLE}
- **Hermes local model:** ${HERMES_ID:-NOT AVAILABLE}
- **iQuest Coder local model:** ${IQUEST_ID:-NOT AVAILABLE}
- **LLaVA vision:** ${LLAVA_ID:-NOT AVAILABLE}
- **DeepSeek local:** ${DEEPSEEK_ID:-NOT AVAILABLE} (advisory via API regardless)
- **OpenAI:** advisory via tools/qsb_consult_external.py (gpt-4o, gpt-4o-mini)
- **DeepSeek API:** advisory via tools/qsb_consult_external.py
- **Ollama daemon:** $ollama_ok ($wren_curl_ok endpoint)
- **Unreal Editor binary:** $ue_avail at \`$ue_editor\`
- **Unreal project:** $ue_project_avail at \`$ue_project\`
- **team_memory dir:** $mem_dir_ok

## Full ollama list
\`\`\`
$ollama_list
\`\`\`

## Honest gaps
- OpenClaw: no model, lives as a ticket-writer script + JSONL log
- Smoke testers: scripts only, no model
- Maintenance crew: scripts only, no model
EOF

echo "wrote $OUT_JSON"
echo "wrote $OUT_MD"
cat "$OUT_JSON"
