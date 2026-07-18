#!/usr/bin/env bash
# Spawn full belief-driven trader fleet (31 baseline + 3 strategy + 3 ensemble = 37)
set -u
cd /vaults/nvme0/qsb_tower_v1
LOG=logs/intelligence

# baseline (worker_id, venue, instrument, hold_secs, sim_units)
BASELINE=(
  "btc:binance:BTCUSDT:60:0.0001"
  "eth:binance:ETHUSDT:60:0.002"
  "bnb:binance:BNBUSDT:60:0.01"
  "eur:oanda:EUR_USD:120:1000"
  "gbp:oanda:GBP_USD:120:1000"
  "jpy:oanda:USD_JPY:120:1000"
  "aud:oanda:AUD_USD:120:1000"
  "chf:oanda:USD_CHF:120:1000"
  "eurgbp:oanda:EUR_GBP:120:1000"
  "xau:oanda:XAU_USD:120:10"
  "xag:oanda:XAG_USD:120:100"
  "wti:oanda:WTICO_USD:120:10"
  "bco:oanda:BCO_USD:120:10"
  "spx:oanda:SPX500_USD:120:1"
  "nas:oanda:NAS100_USD:120:1"
  "dow:oanda:US30_USD:120:1"
  "natgas:oanda:NATGAS_USD:120:100"
  "spy:alpaca:SPY:90:1"
  "aapl:alpaca:AAPL:90:1"
  "qqq:alpaca:QQQ:90:1"
  "tsla:alpaca:TSLA:90:1"
  "nvda:alpaca:NVDA:90:1"
  "msft:alpaca:MSFT:90:1"
  "dia:alpaca:DIA:90:1"
  "xlf:alpaca:XLF:90:5"
  "gld:alpaca:GLD:90:2"
  "coin:alpaca:COIN:90:1"
  "iwm:alpaca:IWM:90:2"
)
for spec in "${BASELINE[@]}"; do
  IFS=':' read -r w venue inst hold units <<< "$spec"
  nohup python3 tools/qsb_belief_driven_trader.py --worker-id "belief_driven_${w}" \
    --venue "$venue" --instrument "$inst" \
    --hold-secs "$hold" --sim-units "$units" \
    >"$LOG/trader_${w}.log" 2>&1 </dev/null &
done

# Strategy demos
nohup python3 tools/qsb_belief_driven_trader.py --worker-id belief_driven_btc_momentum --venue binance --instrument BTCUSDT --hold-secs 60 --sim-units 0.0001 --strategy momentum >"$LOG/trader_btc_momentum.log" 2>&1 </dev/null &
nohup python3 tools/qsb_belief_driven_trader.py --worker-id belief_driven_eur_meanrevert --venue oanda --instrument EUR_USD --hold-secs 120 --sim-units 1000 --strategy mean_revert >"$LOG/trader_eur_meanrevert.log" 2>&1 </dev/null &

# Ensembles
nohup python3 tools/qsb_ensemble_coordinator.py --instrument BTCUSDT --venue binance --sim-units 0.0005 >"$LOG/trader_ensemble_btcusdt.log" 2>&1 </dev/null &
nohup python3 tools/qsb_ensemble_coordinator.py --instrument EUR_USD --venue oanda --sim-units 1000 >"$LOG/trader_ensemble_eurusd.log" 2>&1 </dev/null &

disown -a 2>/dev/null
sleep 5
echo "trader procs: $(pgrep -fc qsb_belief_driven_trader)"
echo "ensemble procs: $(pgrep -fc qsb_ensemble_coordinator)"
