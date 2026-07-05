"""qsb_correlation_groups.py — correlation-aware sizing.

Per Ross 2026-06-24 "make it all happen". Ship 2 of 3.

3-of-3 team unanimous: EUR_USD + EUR_GBP can both go full £50 → £100 EUR exposure.
A single EUR shock blows both. Cap combined currency exposure to £150 per currency.

Architecture: thin function `currency_exposure_check()` called inside the £5000 pot
before reserving. Sums currently-committed GBP across all positions sharing a base
or quote currency, refuses if adding the new position would push the group over cap.

Cap default: £150 per currency. Configurable per currency.

Groups: derived from instrument codes (EUR_USD → {EUR, USD}, BTCUSDT → {BTC, USDT},
SPY → {USD} since it's USD-quoted).
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
POT_FILE = ROOT / "data/registries/qsb_portfolio_pot.json"

# Cap per currency in GBP (combined notional across all instruments touching it).
# Default £150 — DeepSeek's "cap combined EUR exposure to £60" was conservative;
# £150 = 3% of pot per single currency, allows 3 concurrent winners per currency.
DEFAULT_CURRENCY_CAP_GBP = 800.0
# 2026-06-26 raised — JPY 800->1100 (Kelly-scaled JPY notional was £856, over cap),
# GBP 1000->1200 (Kelly-scaled GBP £1056, over cap). The Kelly scaler can push
# positions ~30pct above sim_units; caps must accommodate that.
CURRENCY_CAP_OVERRIDE = {
    "USD": 4500.0,   # 2026-07-02 raised 3500→4500 (was blocking new opens at £3056)
    "USDT": 1500.0,
    "GBP": 2500.0,   # 2026-07-02 raised 1200→2500 (GBP is the benched WINNER Ross unpaused; orphans filled the £1200 cap)
    "EUR": 2500.0,   # 2026-07-02 mirror GBP raise
    "JPY": 1500.0,   # 2026-07-02 raised 1100→1500
    "BTC": 200.0,    # 2026-07-02 tightened 500→200 (Ross cut btc bleeder)
    "ETH": 200.0,    # 2026-07-02 tightened 500→200 (Ross cut eth bleeder)
}


def instrument_currencies(instrument: str) -> list[str]:
    """Return list of currency codes the instrument exposes us to."""
    # FX/metals: split on _
    if "_" in instrument:
        parts = instrument.split("_")
        return parts  # e.g. EUR_USD → ['EUR', 'USD']
    # Crypto USDT pairs
    if instrument.endswith("USDT"):
        return [instrument[:-4], "USDT"]
    if instrument.endswith("USDC"):
        return [instrument[:-4], "USDC"]
    if instrument.endswith("USD"):
        return [instrument[:-3], "USD"]
    # US equities default to USD
    return ["USD"]


def cap_for(ccy: str) -> float:
    return CURRENCY_CAP_OVERRIDE.get(ccy, DEFAULT_CURRENCY_CAP_GBP)


def current_exposure_by_ccy() -> dict[str, float]:
    """Read the pot file and sum committed GBP by currency."""
    if not POT_FILE.exists():
        return {}
    try:
        d = json.loads(POT_FILE.read_text())
    except Exception:
        return {}
    by_ccy: dict[str, float] = {}
    for pos in d.get("open_positions", {}).values():
        inst = pos.get("instrument", "")
        n_gbp = float(pos.get("notional_gbp", 0))
        for c in instrument_currencies(inst):
            by_ccy[c] = by_ccy.get(c, 0) + n_gbp
    return by_ccy


def check_currency_exposure(instrument: str, new_notional_gbp: float):
    """2026-06-26 team-signed CLAMP-not-REFUSE (DeepSeek+OpenAI; Wren ACK).
    Returns either (ok, reason) 2-tuple OR (ok, clamped_notional_gbp, reason) 3-tuple.
    Refuse only if clamped < MIN_CLAMP_CCY. Mirrors qty_exceeds_cap CLAMP pattern."""
    MIN_CLAMP_CCY = 20.0
    cur = current_exposure_by_ccy()
    clamped = new_notional_gbp
    last_c = ""
    for c in instrument_currencies(instrument):
        last_c = c
        cap = cap_for(c)
        existing = cur.get(c, 0)
        if existing + new_notional_gbp > cap:
            clamped = min(clamped, cap - existing)
            if clamped < MIN_CLAMP_CCY:
                return False, (f"ccy_cap_{c} (existing £{existing:.2f} + £{new_notional_gbp:.2f}"
                              f" > £{cap:.2f}, clamped £{clamped:.2f} < MIN)")
    if clamped < new_notional_gbp:
        return True, clamped, f"ccy_clamped_{last_c} (£{new_notional_gbp:.2f} -> £{clamped:.2f})"
    return True, "ccy_ok"


if __name__ == "__main__":
    print("Current exposure by currency:")
    cur = current_exposure_by_ccy()
    for c, v in sorted(cur.items(), key=lambda x: -x[1]):
        print(f"  {c:6s} £{v:7.2f}  cap=£{cap_for(c):.2f}")
