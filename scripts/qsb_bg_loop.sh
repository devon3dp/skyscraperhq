#!/bin/bash
cd /vaults/nvme0/qsb_tower_v1
exec >> logs/qsb_bg_loop.log 2>&1
while true; do
  echo "=== $(date -u +%FT%TZ) tick ==="
  python3 tools/qsb_ops_tick.py 2>&1 | tail -2
  python3 tools/qsb_trading_daily_snapshot.py 2>&1 | tail -1
  python3 tools/qsb_trading_to_finance_rollup.py 2>&1 | tail -1
  [ -f tools/qsb_stripe_webhook_handler.py ] && python3 tools/qsb_stripe_order_poller.py 2>&1 | tail -1
  [ -f tools/qsb_oanda_position_monitor.py ] && python3 tools/qsb_oanda_position_monitor.py 2>&1 | tail -1
  [ -f tools/qsb_news_crawler.py ] && python3 tools/qsb_news_crawler.py 2>&1 | tail -1
  python3 tools/qsb_tunnel_monitor.py 2>&1 | tail -1
  curl -fsS http://localhost:8765/api/sentinels/run -m 8 >/dev/null 2>&1
  sleep 300
done
