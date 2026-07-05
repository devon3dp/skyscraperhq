#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
echo "=== team roster (latest probe) ==="
[[ -f data/registries/qsb_team_model_roster_latest.json ]] && jq -r '
  "  wren  : \(.wren_local_model_id)",
  "  hermes: \(.hermes_local_model_id)",
  "  iquest: \(.iquest_coder_local_model_id)",
  "  unreal_editor_running: TBD",
  "  ollama: \(.ollama_endpoint_reachable)"
' data/registries/qsb_team_model_roster_latest.json
echo ""
echo "=== last model calls (tail 5) ==="
[[ -f data/registries/qsb_team_last_model_calls.json ]] && jq -r '.[-5:] | .[] | "  \(.ts)  \(.member)/\(.model)  success=\(.success)  \(.wall_s)s  \(.task_head[0:80])"' data/registries/qsb_team_last_model_calls.json 2>/dev/null
echo ""
echo "=== latest consensus ==="
[[ -f data/registries/qsb_team_consensus_latest.json ]] && jq -r '"task: \(.task)\nconsensus: \(.consensus)\navailable: \(.available)/\(.reviewers | length)"' data/registries/qsb_team_consensus_latest.json 2>/dev/null
echo ""
echo "=== Wren continuity ==="
head -20 data/team_memory/wren/wren_continuity_report.md 2>/dev/null | tail -15
echo ""
echo "=== daemon ==="
./scripts/qsb_team_daemon_status.sh
