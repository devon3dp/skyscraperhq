#!/usr/bin/env bash
# Install the two QSB box grinders as boot-proof systemd services.
# Runs FROM the tower against each box's cockpit (loop lives tower-side -> survives box reboots).
# Vaulted sudo password (pw only). Usage: bash deploy/grinder/install_grinders.sh
set -euo pipefail
ROOT=/vaults/nvme0/qsb_tower_v1
SUDO_PW="$(grep -E '^SUDO_PASSWORD=' "$ROOT/floors/floor_28_security_department/vault/.env.sudo" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')"
s() { echo "$SUDO_PW" | sudo -S "$@"; }

for svc in tp acer; do
  s cp "$ROOT/deploy/grinder/qsb-grinder-$svc.service" /etc/systemd/system/qsb-grinder-$svc.service
done
s systemctl daemon-reload
s systemctl enable --now qsb-grinder-tp.service
s systemctl enable --now qsb-grinder-acer.service
echo "=== status ==="
systemctl is-active qsb-grinder-tp.service qsb-grinder-acer.service
systemctl is-enabled qsb-grinder-tp.service qsb-grinder-acer.service
