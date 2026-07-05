================================================================================
2026-06-11 Ross authorization — operational payments + e-commerce go-live:

The skyscraper may, ONLY via the two-key flow at tools/qsb_purchase_request.py:
- Spend real money on operational purchases up to per-request and per-day caps
- Process live customer payments through F61-F65 + F154-F163 dropship sites
- Submit supplier orders on receipt of customer payment

Gates that NOW flip TRUE:
- live_payments_enabled                    = true   (Stripe live keys allowed)
- operational_spend_via_purchase_request   = true   (tools/qsb_purchase_request.py)
- live_listings_publishing_enabled         = true   (15 dropship sites may publish live)

Gates that REMAIN LOCKED FALSE:
- real_money_live_trading_enabled          = false  (no live trading)
- openclaw_real_tool_execution_enabled     = false
- autonomous_dispatch_enabled              = false  (no spend without per-request Ross OK)
- worker_execution_enabled                 = false  (workers don't initiate provider calls)
- web_access_autonomous_enabled            = false

Hard caps (raise via further CLAUDE.md edit):
- per_request_cap_gbp:       £100
- per_day_cap_gbp:           £200
- single_stripe_charge_max:  £500
- daily_stripe_volume_max:   £5,000

Authorized vendors (closed list): namecheap.com, netlify.com, wise.com, stripe.com,
squareup.com, aliexpress.com, alibaba.com, GitHub (paid plans), Cloudflare paid tiers.

Authorized categories: domain, hosting, supplier_order, operations, tooling.

All real-money flows audit to:
- data/registries/qsb_purchase_request_ledger.jsonl
- data/registries/qsb_floor44_master_book.json
- data/registries/qsb_tower_activity_tail.jsonl

Wren will not act on any of these without Ross's per-request approval recorded in
the purchase_request ledger.
================================================================================
