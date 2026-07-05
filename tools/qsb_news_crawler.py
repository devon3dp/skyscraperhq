#!/usr/bin/env python3
"""qsb_news_crawler.py — pull market news headlines for tracked tickers.

Uses yfinance Ticker(s).news.
Writes to data/registries/qsb_market_news_feed.jsonl (append-only).
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from datetime import datetime, timezone

REG = Path('/vaults/nvme0/qsb_tower_v1/data/registries')
FEED = REG / 'qsb_market_news_feed.jsonl'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def crawl(symbols):
    import yfinance as yf
    seen_p = REG / 'qsb_market_news_seen.json'
    seen = set(json.loads(seen_p.read_text())) if seen_p.exists() else set()
    added = 0
    for s in symbols:
        try:
            news = yf.Ticker(s).news[:10]
        except Exception as e:
            continue
        for n in news:
            c = n.get('content', n) if isinstance(n.get('content'), dict) else n
            uid = c.get('id') or n.get('id') or n.get('uuid') or c.get('title','')[:80]
            if uid in seen: continue
            seen.add(uid)
            row = {
                'ts': utcnow(), 'ticker': s,
                'title': c.get('title','') or n.get('title',''),
                'summary': c.get('summary','') or c.get('description',''),
                'publisher': (c.get('provider') or {}).get('displayName','') if isinstance(c.get('provider'), dict) else n.get('publisher',''),
                'link': (c.get('canonicalUrl') or {}).get('url','') if isinstance(c.get('canonicalUrl'), dict) else n.get('link',''),
                'published_ts': c.get('pubDate') or c.get('displayTime') or n.get('providerPublishTime'),
                'uuid': uid,
            }
            with FEED.open('a') as f:
                f.write(json.dumps(row) + '\n')
            added += 1
    seen_p.write_text(json.dumps(sorted(seen)))
    return added

if __name__ == '__main__':
    SYMS = sys.argv[1:] if len(sys.argv) > 1 else [
        'VOD.L','BP.L','HSBA.L','BARC.L','GSK.L','RIO.L','SHEL.L','LLOY.L','TSCO.L','AZN.L',
        'SPY','QQQ','AAPL','MSFT','NVDA','AMZN','META','GOOGL','TSLA','JPM',
        'BTC-USD','ETH-USD','GBP=X','EUR=X','GC=F','CL=F',
    ]
    n = crawl(SYMS)
    print(f'crawled news for {len(SYMS)} tickers, {n} new headlines added')
