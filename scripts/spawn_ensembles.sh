#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
LOG=logs/intelligence

ENSEMBLES=(
  "BTCUSDT:binance:0.0002"
  "ETHUSDT:binance:0.005"
  "BNBUSDT:binance:0.02"
  "EUR_USD:oanda:1000"
  "GBP_USD:oanda:1000"
  "USD_JPY:oanda:1000"
  "AUD_USD:oanda:1000"
  "USD_CHF:oanda:1000"
  "EUR_GBP:oanda:1000"
  "XAU_USD:oanda:10"
  "XAG_USD:oanda:100"
  "WTICO_USD:oanda:10"
  "BCO_USD:oanda:10"
  "SPX500_USD:oanda:1"
  "NAS100_USD:oanda:1"
  "US30_USD:oanda:1"
  "NATGAS_USD:oanda:100"
  "SPY:alpaca:1"
  "AAPL:alpaca:1"
  "QQQ:alpaca:1"
  "TSLA:alpaca:1"
  "NVDA:alpaca:1"
  "MSFT:alpaca:1"
)

for spec in "${ENSEMBLES[@]}"; do
  IFS=':' read -r inst venue units <<< "$spec"
  short=$(echo "$inst" | tr 'A-Z' 'a-z' | tr -d '_')
  nohup python3 tools/qsb_ensemble_coordinator.py --instrument "$inst" --venue "$venue" --sim-units "$units" \
    >"$LOG/trader_ensemble_${short}.log" 2>&1 </dev/null &
done
disown -a 2>/dev/null
sleep 5
echo "ensembles alive: $(pgrep -fc qsb_ensemble_coordinator)"
