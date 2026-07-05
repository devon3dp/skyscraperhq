#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
F=data/registries/qsb_wren_second_in_command_status.json
[[ -f $F ]] || { echo "no Wren SIC status"; exit 1; }
RC=$(jq -r .tick_result "$F")
RP=$(jq -r .report_path "$F")
echo "wren_sic_result=$RC report=$RP"
[[ "$RC" == "ok" && -f "$RP" ]] && exit 0 || exit 1
