#!/usr/bin/env bash
set -e
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.database
python3 tests/validate_tower.py
echo "QSB Tower V1 setup complete."
