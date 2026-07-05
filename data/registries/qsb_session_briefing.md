# QSB Tower · Session Briefing

*Generated 2026-06-11T15:35:28.878918Z*

## State Today
- Floors: **165**
- Workers: **8,586**
- Certified: **766**
- OANDA: £43.5892 realized · 5 open · 31 closed
- LSE F60: £99,751.52 · 6 positions
- F44 packets: 26 · venues 3
- F47 records today: **135**
- Ops float: £77.33
- Provider spend: $0.0024 / $5.00

## Last 12 actions (F47)
- **[14:50:14]** `live_data_endpoint_built` — Built /api/floor/N/live endpoint that returns: name, interior_brief, worker_count, workers_sample, recent_events (F47 mentions), live_data (
- **[14:59:33]** `no_demos_canonical_endpoint` — Ross: NO DEMOS. Built /api/tower/state canonical truth source. Every metric traces to a registry file. Dashboard + Godot both fetch from thi
- **[15:01:20]** `reconciled_oanda_pnl` — OANDA pnl reconciled to canonical truth: total realized £43.5892 (£-20.6503 historical + £64.2395 today). Both dashboard surfaces now show s
- **[15:06:11]** `dashboard_truth_reconciled` — Two /api/health endpoints reconciled to canonical OANDA pnl. cap_usd now reads from auth registry (£5 not £1). Both endpoints + Godot now sh
- **[15:07:03]** `placeholder_rows_removed` — Removed Entropy + Variance placeholder rows from cockpit.js — they were literal stubs being shown to user.
- **[15:08:40]** `no_demos_audit_pass_1` — Audit pass 1: /api/health + /api/tower/state reconciled to same canonical pnl source. Entropy/Variance placeholder rows removed from cockpit
- **[15:15:27]** `godot_screen_wired_to_live` — Godot floor interior wall-screen now reads /api/floor/N/live (rich) instead of /intro (terse). Shows real floor name, archetype, worker coun
- **[15:16:29]** `f47_archetype_set_to_embassy` — F47 manifest archetype upgraded from generic to embassy. Palette: wren green + warm white + brass. Mood: reverent + warm + watchful. Furnitu
- **[15:20:45]** `audit_pass_2_status` — Audit pass 2: 24/31 dashboard JS files reference /api/ endpoints (good). Remaining stub-like rows are real labels with real timestamps. Godo
- **[15:22:28]** `godot_data_format_fixed` — floor_fitout.json regenerated in Dictionary-keyed format Godot expects. 164 floors. Bug at FloorInteriorFactory.gd:280 resolved.
- **[15:31:11]** `real_activity_feed_endpoint` — Added /api/feed/activity that returns REAL events from F47 records + activity tail. No template packets. Ticker patched to fetch from this. 
- **[15:32:03]** `real_telemetry_endpoint_set` — Real telemetry endpoints: /api/tower/state · /api/health · /api/floor/N/live · /api/feed/activity. All return real-file-backed data. Ticker 

## Money
- Ops float: £77.33
- Per-request cap: £100.00
- Per-day cap: £200.00

## Owned Domains
- skyscraperhq.uk · £5.48 · primary_master
- quilltree.co.uk · £5.48 · shop_hero
- pawsworth.co.uk · £5.48 · shop_hero
- greenhouselane.co.uk · £5.48 · shop_hero
- stretchfitness.xyz · £0.53 · shop_hero

## Public State
- Public tunnel: https://exterior-these-ambassador-regions.trycloudflare.com
- GitHub repo: https://github.com/devon3dp/skyscraperhq (private)
- Stripe: LIVE + verified (test mode in tower)
- Netlify: deploy pending Ross click

## Open Loops
- DNS records → Namecheap for skyscraperhq.uk
- Stripe LIVE secret key → flip 150 Payment Links live
- Ticker UI rebuild (in progress)
- Template packets in /api/unified (need replacement)