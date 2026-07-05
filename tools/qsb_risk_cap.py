#!/usr/bin/env python3
"""qsb_risk_cap.py — convert (venue, instrument, units) → GBP notional exposure
and enforce a hard per-trade ceiling.

Ross's rule: max £1000 NOTIONAL per single paper trade. Defense in depth on
top of the venue-level guardrails (Floor 41/42/43 already block large unit
counts; this is the floor-47 layer).

Used by tools/qsb_train_and_trade_cohort.py before placement.

API:
    from tools.qsb_risk_cap import check_gbp_cap, GBP_CAP_PER_TRADE
    ok, gbp, reason = check_gbp_cap(venue, instrument, units)

GBP/USD live price is fetched from OANDA practice; if that fails we fall back
to a conservative pinned rate so the cap can never silently disappear.
"""

from __future__ import annotations
import json, os, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
GBP_CAP_PER_TRADE = 1000.0
FALLBACK_GBP_USD = 1.30   # If OANDA pricing fails, assume £1 = $1.30 conservatively.


def _load_oanda_env() -> tuple[str, str]:
    """Read OANDA credentials from the Floor 28 vault."""
    env_path = ROOT / "floors/floor_28_security_department/vault/.env.oanda_practice"
    token = ""
    account = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line: continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip("'").strip('"')
            if k == "OANDA_API_TOKEN": token = v
            elif k == "OANDA_ACCOUNT_ID": account = v
    return token, account


def _fetch_oanda_prices(instruments: list[str]) -> dict:
    """Return {instr: mid_price_usd}. Empty dict on failure."""
    token, account = _load_oanda_env()
    if not (token and account):
        return {}
    url = (f"https://api-fxpractice.oanda.com/v3/accounts/{account}/pricing"
           f"?instruments={','.join(instruments)}")
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.loads(r.read().decode())
        out = {}
        for p in d.get("prices", []):
            bid = float(p.get("bids", [{}])[0].get("price", 0))
            ask = float(p.get("asks", [{}])[0].get("price", 0))
            if bid and ask:
                out[p["instrument"]] = (bid + ask) / 2.0
        return out
    except Exception:
        return {}


def gbp_per_usd() -> float:
    """Return GBP/USD (i.e., £ per $1). Falls back to 1/FALLBACK_GBP_USD."""
    prices = _fetch_oanda_prices(["GBP_USD"])
    p = prices.get("GBP_USD")
    if p and p > 0:
        return 1.0 / p   # GBP_USD quote is USD per GBP; invert to get GBP per USD
    return 1.0 / FALLBACK_GBP_USD


def usd_exposure_for(venue: str, instrument: str, units_or_qty: float) -> float:
    """Return the USD notional value of a trade of size `units_or_qty`.

    OANDA conventions (X_Y):
      · 1 unit of trade = 1 unit of the BASE currency X
      · price quote is "Y per X"
      · if X == USD     → exposure = units (already USD)
      · if Y == USD     → exposure = units * price_USD_per_X
      · otherwise (cross): fetch X_USD if available, else fall back conservatively
    """
    if venue == "oanda_practice":
        if "_" not in instrument:
            return float(units_or_qty) * 100.0  # conservative
        base, quote = instrument.split("_", 1)
        if base == "USD":
            return float(units_or_qty)
        if quote == "USD":
            prices = _fetch_oanda_prices([instrument])
            mid = prices.get(instrument, 0)
            if not mid:
                return float(units_or_qty) * 100.0
            return float(units_or_qty) * mid
        # Cross pair (e.g., EUR_GBP) — convert base to USD via base_USD
        cross_instr = f"{base}_USD"
        prices = _fetch_oanda_prices([cross_instr])
        mid = prices.get(cross_instr, 0)
        if not mid:
            return float(units_or_qty) * 100.0
        return float(units_or_qty) * mid
    if venue == "binance_testnet":
        # Binance positional sizing uses quote_qty_usdt directly.
        return float(units_or_qty)
    if venue == "alpaca_paper":
        # Alpaca placement is shares * price; conservatively assume $50 per share
        # for unknown stocks until the wrapper resolves a live quote.
        return float(units_or_qty) * 50.0
    return float(units_or_qty) * 100.0   # unknown venue → conservative


def gbp_exposure_for(venue: str, instrument: str, units_or_qty: float) -> float:
    usd = usd_exposure_for(venue, instrument, units_or_qty)
    return usd * gbp_per_usd()


def check_gbp_cap(venue: str, instrument: str,
                    units_or_qty: float) -> tuple[bool, float, str]:
    """Return (ok, computed_gbp_exposure, reason).

    ok=True  → trade is within the £1000 notional ceiling.
    ok=False → reason explains why.
    """
    if units_or_qty <= 0:
        return False, 0.0, "units must be positive"
    gbp = gbp_exposure_for(venue, instrument, units_or_qty)
    if gbp > GBP_CAP_PER_TRADE:
        return False, gbp, (
            f"would exceed £{GBP_CAP_PER_TRADE:.0f} notional cap "
            f"(computed £{gbp:.2f} for {units_or_qty} {instrument} on {venue})"
        )
    return True, gbp, "within_cap"


def max_units_within_cap(venue: str, instrument: str,
                          step: float = 1.0,
                          start_units: float = 1.0) -> float:
    """Find the largest units count that stays at or under the £1000 cap.

    Used by strategy authors to set sensible defaults per instrument.
    """
    if venue == "binance_testnet":
        # quote_qty IS in USDT; max = £1000 → ~$1300 at current GBP/USD.
        return GBP_CAP_PER_TRADE / gbp_per_usd()
    if venue == "alpaca_paper":
        # Approximation only; use 1-share steps.
        return max(1.0, GBP_CAP_PER_TRADE / (gbp_per_usd() * 50.0))
    # OANDA: compute exposure per unit, divide cap by that.
    one_unit_gbp = gbp_exposure_for(venue, instrument, 1.0)
    if one_unit_gbp <= 0:
        return start_units
    raw = GBP_CAP_PER_TRADE / one_unit_gbp
    # Snap to multiples of step
    return float(int(raw / step) * step)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", required=True)
    ap.add_argument("--instrument", required=True)
    ap.add_argument("--units", required=True, type=float)
    args = ap.parse_args()
    ok, gbp, reason = check_gbp_cap(args.venue, args.instrument, args.units)
    print(f"  venue:       {args.venue}")
    print(f"  instrument:  {args.instrument}")
    print(f"  units:       {args.units}")
    print(f"  GBP/USD:     {gbp_per_usd():.4f}")
    print(f"  USD exposure: ${usd_exposure_for(args.venue, args.instrument, args.units):.2f}")
    print(f"  GBP exposure: £{gbp:.2f}")
    print(f"  cap (£):     £{GBP_CAP_PER_TRADE:.0f}")
    print(f"  status:      {'WITHIN CAP' if ok else 'BLOCKED'}")
    print(f"  reason:      {reason}")
    # Suggest max units within cap
    max_u = max_units_within_cap(args.venue, args.instrument)
    print(f"  max safe:    {max_u} units")
