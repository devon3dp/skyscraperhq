#!/usr/bin/env bash
# Spawn full belief-driven trader fleet with setsid (truly detached).
cd /vaults/nvme0/qsb_tower_v1
LOG=logs/intelligence

BASELINE=(
  "btc:binance:BTCUSDT:60:0.005"
  "eth:binance:ETHUSDT:60:0.1"
  "bnb:binance:BNBUSDT:60:0.5"
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
  # 2026-06-23 OANDA tier-3 expansion (Wren pick — Ross sign-off):
  "de30:oanda:DE30_EUR:120:1"
  "jp225:oanda:JP225_USD:120:1"
  "us10y:oanda:USB10Y_USD:120:1"
  "uk10y:oanda:UK10YB_GBP:120:1"
  "xcu:oanda:XCU_USD:120:100"
  "wheat:oanda:WHEAT_USD:120:100"
  # 2026-06-23 Binance tier-1 expansion (Hermes pick — Ross sign-off):
  "sol:binance:SOLUSDT:60:0.1"
  "ada:binance:ADAUSDT:60:50"
  "xrp:binance:XRPUSDT:60:50"
  "dot:binance:DOTUSDT:60:10"
  "avax:binance:AVAXUSDT:60:2"
  "link:binance:LINKUSDT:60:5"
  # 2026-06-27 Binance tier-2 expansion (3/3 team unanimous + Ross sign-off):
  "ltc:binance:LTCUSDT:60:1"
  "trx:binance:TRXUSDT:60:1000"
  "doge:binance:DOGEUSDT:60:2000"
  "pol:binance:POLUSDT:60:2000"
  "arb:binance:ARBUSDT:60:500"
  # 2026-06-27 Binance tier-2 expansion (2/3 team votes + Ross sign-off):
  "near:binance:NEARUSDT:60:50"
  "atom:binance:ATOMUSDT:60:50"
  "apt:binance:APTUSDT:60:100"
  "icp:binance:ICPUSDT:60:50"
  "op:binance:OPUSDT:60:500"
)

PAUSED_FILE=data/registries/qsb_paused_workers.json
is_paused() {
  [ -f "$PAUSED_FILE" ] || return 1
  python3 -c "import json,sys; d=json.load(open('$PAUSED_FILE')); sys.exit(0 if 'belief_driven_$1' in d else 1)"
}

for spec in "${BASELINE[@]}"; do
  IFS=':' read -r w venue inst hold units <<< "$spec"
  if is_paused "$w"; then
    echo "skip paused: belief_driven_$w"
    continue
  fi
  if pgrep -f "qsb_belief_driven_trader.py.*belief_driven_${w}\b" >/dev/null; then
    continue
  fi
  setsid python3 tools/qsb_belief_driven_trader.py \
    --worker-id "belief_driven_${w}" \
    --venue "$venue" --instrument "$inst" \
    --hold-secs "$hold" --sim-units "$units" \
    </dev/null >"$LOG/trader_${w}.log" 2>&1 &
done

# Strategy demos
for spec in "btc_momentum:binance:BTCUSDT:60:0.0005:momentum" \
            "eur_meanrevert:oanda:EUR_USD:120:1000:mean_revert" \
            "xau_breakout:oanda:XAU_USD:120:10:breakout"; do
  IFS=':' read -r w venue inst hold units strat <<< "$spec"
  if pgrep -f "qsb_belief_driven_trader.py.*belief_driven_${w}\b" >/dev/null; then continue; fi
  setsid python3 tools/qsb_belief_driven_trader.py \
    --worker-id "belief_driven_${w}" \
    --venue "$venue" --instrument "$inst" \
    --hold-secs "$hold" --sim-units "$units" \
    --strategy "$strat" \
    </dev/null >"$LOG/trader_${w}.log" 2>&1 &
done

sleep 4
echo "traders alive: $(pgrep -fc qsb_belief_driven_trader)"
