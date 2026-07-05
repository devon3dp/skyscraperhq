#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

./scripts/oanda_paper_strategy_lab.sh "$INSTRUMENTS" > data/runtime/oanda_paper_strategy_lab_output.json

PROMPT="$(cat data/runtime/oanda_paper_strategy_lab_output.json)

Kernel, review this Floor 41 OANDA Paper Strategy Lab output.
This is paper research only.
Do not place orders.
Do not enable live trading.
Do not enable practice order execution.
Do not enable workers.
Do not enable OpenClaw.
Do not enable autonomous dispatch.
Give a concise tactical read, risk warning, and what to observe next."

./scripts/qsb_kernel_chat.sh "$PROMPT"
