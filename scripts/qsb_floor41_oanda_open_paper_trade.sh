#!/usr/bin/env bash
# QSB Floor 41 OANDA — Open Paper Trade (CLI)
# Usage: qsb_floor41_oanda_open_paper_trade.sh INSTRUMENT DIRECTION UNITS ENTRY_REASON
# Example: qsb_floor41_oanda_open_paper_trade.sh EUR_USD buy 1000 "trend_signal"

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
[ -f .env.oanda_practice ] && { set -a; . ./.env.oanda_practice; set +a; }

if [ "$#" -lt 4 ]; then
  echo "usage: $0 INSTRUMENT DIRECTION UNITS ENTRY_REASON"
  exit 2
fi

python3 -m tower.qsb_floor41_oanda open "$1" "$2" "$3" "$4"
