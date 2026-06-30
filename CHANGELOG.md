
## 2026-06-30 18:30 UTC
- QSB Tower trader fix: broker placement success rate jumped 0.4% → 99.3% sustained
- Root cause: gate max_qty_per_order=1.0 was clamping ADA/XRP/DOT/AVAX/SOL orders below Binance $5 NOTIONAL min — bumped to 1000.0
- Bumped crypto ensemble sim-units (BTC 0.0001→0.0002, ETH 0.002→0.005, BNB 0.01→0.02) so each order clears min-notional
- Pot orphan reconcile: closed 37 stuck positions across alpaca_paper / binance_testnet / oanda_practice — freed £2956 of £5000 cap
- HQ ↔ ThinkPad CEO bidirectional heartbeats live (30s + 15s cadence) with auto-restart resilience
- NVIDIA RTX 5070 Ti GSP fall-off-bus permanently fixed via pcie_aspm=off + display moved to AMD iGPU
- 10-min REAL window: 715 closes, 58.0% WR, +£8.28 net PnL (paper/practice/testnet — real-money still locked)

## 2026-06-27 12:10 UTC
- QSB Tower trader upgrade: £1 minimum-profit gate + trailing stop tighten (locks 70% of high-water mark)
- 10 new Binance crypto traders spawned for weekend coverage (PEPE, WIF, BONK, JUP, SEI, TIA, INJ, AAVE, UNI, FIL)
- Dashboard V8: traffic lights, river flow, broker flow, streak bars, £1-gate counter
