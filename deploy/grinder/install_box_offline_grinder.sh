#!/usr/bin/env bash
# install_box_offline_grinder.sh — deploy the OFFLINE-FIRST box grind agent +
# its box-side autonomous scheduler onto a Windows worker box.
#
# This is the piece that makes "HQ offline -> box keeps working" literally true:
# a Windows Scheduled Task (QSB_Offline_Grinder) runs the grind+rollup on the
# BOX's own timer every few minutes, calling only the local Ollama. HQ never
# has to kick it. HQ's only job is transport (scp bundle in, scp results out),
# which is out-of-band and best-effort.
#
# Usage: bash deploy/grinder/install_box_offline_grinder.sh <thinkpad|acer> [interval_min]
set -euo pipefail
ROOT=/vaults/nvme0/qsb_tower_v1
BOX="${1:?box: thinkpad|acer}"
INTERVAL="${2:-5}"
KEY=/home/ross/.ssh/skyscraper_ed25519
case "$BOX" in
  thinkpad) HOST=192.168.1.91 ;;
  acer)     HOST=192.168.1.41 ;;
  *) echo "unknown box $BOX"; exit 1 ;;
esac
TGT="budds@$HOST"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no \
     -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -i "$KEY")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no \
     -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -i "$KEY")

"${SSH[@]}" "$TGT" 'mkdir "%USERPROFILE%\.qsb" 2>nul & echo ok' >/dev/null 2>&1 || true
"${SCP[@]}" "$ROOT/deploy/qsb_box_grind_agent.py" "$TGT:C:/Users/budds/.qsb/qsb_box_grind_agent.py"
"${SCP[@]}" "$ROOT/deploy/qsb_box_grind_run.cmd"    "$TGT:C:/Users/budds/.qsb/qsb_box_grind_run.cmd"

# Register a boot-proof, HQ-independent scheduled task: runs at logon + repeats
# every INTERVAL minutes. /f overwrites an existing task so this is idempotent.
"${SSH[@]}" "$TGT" \
  "schtasks /create /tn QSB_Offline_Grinder /tr \"C:\\Users\\budds\\.qsb\\qsb_box_grind_run.cmd\" /sc minute /mo $INTERVAL /ru budds /f"

echo "=== installed on $BOX ($HOST); task listing ==="
"${SSH[@]}" "$TGT" "schtasks /query /tn QSB_Offline_Grinder /fo LIST"
