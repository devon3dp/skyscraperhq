#!/usr/bin/env bash
# Runs ON the Raspberry Pi (qsb-reception) after first boot + SSH.
# Installs the front-desk service. No API keys, no local model — routes to tower.
set -euo pipefail

HOME_DIR="/home/qsbpi"
echo "[1/4] files present?"
ls -la "$HOME_DIR/qsb_receptionist.py" "$HOME_DIR/qsb-reception.service"

echo "[2/4] install systemd unit"
sudo cp "$HOME_DIR/qsb-reception.service" /etc/systemd/system/qsb-reception.service
sudo systemctl daemon-reload

echo "[3/4] enable + start"
sudo systemctl enable --now qsb-reception.service
sleep 2

echo "[4/4] smoke"
systemctl is-active qsb-reception.service
curl -s http://127.0.0.1:8080/health || echo "  (health not up yet)"
echo
echo "done — front desk on :8080. Tower wall: \$QSB_TOWER_HUB/quad_monitor"
