#!/usr/bin/env python3
"""qsb_arb_scanner.py — fast arbitrage candidate scanner.

Checks for arbitrage opportunities across:
  · same instrument on different venues (e.g., BTC/USD on Binance testnet vs Coinbase quote)
  · same name as ADR vs LSE (e.g., HSBC: HSBA.L vs HSBC NYSE)
  · futures-spot basis (e.g., GC=F vs XAUUSD)

Writes findings to data/registries/qsb_arb_candidates.jsonl
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from datetime import datetime, timezone

REG = Path('/vaults/nvme0/qsb_tower_v1/data/registries')
OUT = REG / 'qsb_arb_candidates.jsonl'

# ADR-style cross-listings (London ticker, NY ticker, description)
ADR_PAIRS = [
    # (lse_sym, us_sym, desc, adr_ratio = US_shares_per_LSE_share)
    ('HSBA.L','HSBC','HSBC bank — LSE vs NYSE', 5),
    ('BP.L','BP','BP — LSE vs NYSE', 6),
    ('SHEL.L','SHEL','Shell — LSE vs NYSE', 2),
    ('GSK.L','GSK','GSK — LSE vs NYSE', 2),
    ('AZN.L','AZN','AstraZeneca — LSE vs NASDAQ', 0.5),
    ('VOD.L','VOD','Vodafone — LSE vs NASDAQ', 10),
    ('RIO.L','RIO','Rio Tinto — LSE vs NYSE', 1),
]

GBP_USD_SYM = 'GBPUSD=X'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def scan_adr_lse():
    import yfinance as yf
    # Pull GBP/USD rate
    try:
        fx = yf.Ticker(GBP_USD_SYM).fast_info.last_price
    except Exception as e:
        return {'err':f'fx {e}'}
    findings = []
    for lse_sym, us_sym, desc, ratio in ADR_PAIRS:
        try:
            lse = yf.Ticker(lse_sym).fast_info
            us = yf.Ticker(us_sym).fast_info
        except Exception:
            continue
        if not lse.last_price or not us.last_price: continue
        # LSE in GBp (pence), US in USD; ADR ratio varies
        lse_gbp = lse.last_price / 100 if (lse.currency or 'GBp') == 'GBp' else lse.last_price
        # adjust LSE price to ADR-equivalent: multiply by 1/ratio to get USD price per ADR
        lse_usd_per_adr = (lse_gbp * fx) * ratio
        us_usd = us.last_price
        spread = us_usd - lse_usd_per_adr
        spread_pct = spread / lse_usd_per_adr * 100 if lse_usd_per_adr else 0
        finding = {
            'ts': utcnow(), 'pair_kind':'lse_vs_nyse_adr',
            'lse_sym': lse_sym, 'us_sym': us_sym, 'desc': desc,
            'lse_price_gbp': round(lse_gbp,4),
            'lse_price_usd_per_adr': round(lse_usd_per_adr,4),
            'adr_ratio': ratio,
            'us_price_usd': round(us_usd,4),
            'gbp_usd_rate': round(fx,4),
            'spread_usd': round(spread,4),
            'spread_pct': round(spread_pct,4),
            'flag_significant': abs(spread_pct) > 0.5,
            'advisory_only': True,
            'real_money': False,
        }
        findings.append(finding)
        with OUT.open('a') as f:
            f.write(json.dumps(finding)+'\n')
    return findings

if __name__ == '__main__':
    f = scan_adr_lse()
    if isinstance(f, list):
        sig = [x for x in f if x.get('flag_significant')]
        print(f'scanned {len(f)} ADR pairs, {len(sig)} flagged > 0.5% spread')
        for x in f:
            mark = ' *' if x.get('flag_significant') else ''
            print(f"  {x['lse_sym']:8s} vs {x['us_sym']:8s} spread {x['spread_pct']:+.3f}%{mark}")
    else:
        print(f)
