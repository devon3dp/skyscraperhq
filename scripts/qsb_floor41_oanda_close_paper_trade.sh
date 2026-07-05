#!/usr/bin/env bash
# QSB Floor 41 OANDA — Close Paper Trade (CLI)
# Usage: qsb_floor41_oanda_close_paper_trade.sh TRADE_ID CLOSE_REASON

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
[ -f .env.oanda_practice ] && { set -a; . ./.env.oanda_practice; set +a; }

if [ "$#" -lt 2 ]; then
  echo "usage: $0 TRADE_ID CLOSE_REASON"
  exit 2
fi

python3 -m tower.qsb_floor41_oanda close "$1" "$2"
