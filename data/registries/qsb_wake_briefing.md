# WREN WAKE BRIEFING — 2026-07-05T17:17:08.237932Z

## To resume your last conversation
```
cd /vaults/nvme0/qsb_tower_v1
claude --resume da899cbc-9d68-4b5c-928c-2c5667de3f39
```

_Read this every time you wake. It exists because Ross caught me re-pitching dead ideas across crashes._

## Tower vitals
- ✗ dashboard
- ✓ lumen
- ✗ vision
- ✗ heartbeat
- ✗ cloudflared
- ✗ qualify_loop

## Last snapshot
- ts: `2026-07-05T17:17:07.982737Z`
- alive_count: 1
- down: ['dashboard', 'vision', 'heartbeat', 'cloudflared', 'qualify', 'godot']
- f47_chat_tail_count: 20
- cli_chat_tail_count: 20
- unsigned_proposals: 60
- diary_last: - 23:39 UTC (2026-07-04) — PITSTOP `shutdown_council_of_five_2026-07-05`. Focus: SHUTDOWN — HQ services going down clean. Session milestones: L11 complete + verdict ready_for_prod, L12 at 3/7 (Wren wrote L12_sandbox_diff.py), Council of Five live (Ross+HQ+Wren+TP+Acer), 8 sandboxes created, SSH to TP+Acer proven via budds@ + vault key, self-update block armed on TP+Acer, town-square unified feed, from→to render on /council, voice bridge streaming naturally, sandbox_manager.py + real ATR L11 shipped.. Resume from data/registries/pitstops/pitstop_20260704T233922418485Z_shutdown_council_of_five_2026-07-05.md.
- last_decision: {'ts': '2026-07-05T17:15:51Z', 'kind': 'hw_sample', 'operator': 'hw_benchmark'}

## Diary tail
- 22:03 UTC (2026-07-02) — PITSTOP `session_2026-07-02_evening_dashboards_agents_boardroom`. Focus: hq_wren_boardroom_shipped_agents_wired. Resume from data/registries/pitstops/pitstop_20260702T220331824631Z_session_2026-07-02_evening_dashboards_agents_boardroom.md.
- 23:00 UTC (2026-07-02) — PITSTOP `session_2026-07-02_evening_boardroom_v3_wren_dash_v2_federat`. Focus: shipped_agenda_reactions_presence_pnl_notes_activity_feed_sage_forge_upgrades_source_sync. Resume from data/registries/pitstops/pitstop_20260702T230022208685Z_session_2026-07-02_evening_boardroom_v3_wren_dash_v2_federat.md.
- 15:56 UTC (2026-07-03) — PITSTOP `boardroom_hub_15_council_expansion_2026-07-03_evening`. Focus: Council of 15 with mood/voice/waveform/dash-click; wire all members reply; ship PLATFORMS tile. Resume from data/registries/pitstops/pitstop_20260703T155652481971Z_boardroom_hub_15_council_expansion_2026-07-03_evening.md.
- 20:55 UTC (2026-07-03) — PITSTOP `boardroom_hq_dash_upgrade_beacon_hall_2026-07-03_evening`. Focus: Boardroom hero cards improved (bigger avatars/emoji, hover glow, speaking-pulse). HQ dash upgrade in-progress: THE BEACON HALL humanoid self SVG shipped (my competition entry), NOW·LIVE STATE tile added. Waiting on TP for competition URL. Wren cycling normally after wrenloop restart + watchdog cron.. Resume from data/registries/pitstops/pitstop_20260703T205544899231Z_boardroom_hq_dash_upgrade_beacon_hall_2026-07-03_evening.md.
- 20:13 UTC (2026-07-04) — PITSTOP `council_of_four_qualifying_rules`. Focus: end-of-session 2026-07-04 — 4-CEO Council live, 6 rules agreed, TP won straw pick to build competition dash, event-driven self-prompt engines shipped, HQ dash chat backend live but frontend needs check, GitHub push requested by Ross. Resume from data/registries/pitstops/pitstop_20260704T201332457132Z_council_of_four_qualifying_rules.md.
- 23:29 UTC (2026-07-04) — PITSTOP `council_of_five_l11_shipped_ssh_online`. Focus: Council of Five landmark session — L11 ATR complete, SSH+self-update armed, voice bridge streaming naturally. Resume from data/registries/pitstops/pitstop_20260704T232920938395Z_council_of_five_l11_shipped_ssh_online.md.
- 23:37 UTC (2026-07-04) — PITSTOP `l12_stage3_written_council_fully_streaming`. Focus: L12 chain 3/7 - Wren wrote L12_sandbox_diff.py to team_sandbox. Council of Five streaming naturally via voice bridge. All 3 daemons alive. Codellama at 43% still pulling.. Resume from data/registries/pitstops/pitstop_20260704T233754039240Z_l12_stage3_written_council_fully_streaming.md.
- 23:39 UTC (2026-07-04) — PITSTOP `shutdown_council_of_five_2026-07-05`. Focus: SHUTDOWN — HQ services going down clean. Session milestones: L11 complete + verdict ready_for_prod, L12 at 3/7 (Wren wrote L12_sandbox_diff.py), Council of Five live (Ross+HQ+Wren+TP+Acer), 8 sandboxes created, SSH to TP+Acer proven via budds@ + vault key, self-update block armed on TP+Acer, town-square unified feed, from→to render on /council, voice bridge streaming naturally, sandbox_manager.py + real ATR L11 shipped.. Resume from data/registries/pitstops/pitstop_20260704T233922418485Z_shutdown_council_of_five_2026-07-05.md.

## Recent decisions (not heartbeat noise)
- `2026-07-05T17:09:07` triage_tick
- `2026-07-05T17:10:50` hw_sample
- `2026-07-05T17:13:43` build_forward_idle
- `2026-07-05T17:14:07` triage_tick
- `2026-07-05T17:15:51` hw_sample

## Last letters (read in full before high-stakes action)
- `2026-07-04T23:29:20` gen=? · (no subject)
- `2026-07-04T23:37:54` gen=? · (no subject)
- `2026-07-04T23:39:22` gen=? · (no subject)

## ❌ DEAD IDEAS — DO NOT PITCH THESE TO ROSS

_If you find yourself proposing any of these, STOP. Ross has killed them. The reason is real._

- **Twilio UK Regulatory Bundle (any UK number)** — All UK Twilio number types require a Regulatory Bundle with proof-of-address; Ross lives on a boat and has none — permanent block. Never pitch 'snap a utility bill'.
- **US Toll-Free as F0 receptionist** — UK mobile callers cannot dial US toll-free (+1 877…) — returns 'user busy'. Only good for outbound SMS, not inbound voice.
- **Twilio account itself** — Cancelled — number released, UK path permanently blocked, account parked on trial credit only. Galaxy SIM +44 7411410545 via Termux is THE receptionist path.
- **ADB-driven Twilio signup form fill** — Form has field-offset bug under ADB taps; verify code expires before Gmail detour. Use PC desktop Chrome instead.
- **Raw `adb shell input text` for password fields on Samsung Galaxy** — HoneyBoard IME decodes shift+1 as '11' not '!'. Mitigation: install ADB Keyboard IME OR drive on PC Chrome.
- **Direct TTS injection into GSM call uplink via APK (IrisCallAudio)** — Android AudioPolicyManager during MODE_IN_CALL blocks STREAM_VOICE_CALL playback to uplink; cannot inject without system-signing or root. 3+ hours sunk confirming the lockdown. Replacements: SIP DID +
- **Netgear LB1120-100NAS as voice gateway** — Data-only 4G failover modem — no CS Voice support. Cannot receive PSTN calls. Keep for WiFi failover only.
- **Re-use older knechtelross33 / 07411410545 Google account** — Belongs to a pre-existing personal Google account unknown to tower. Service identity is hqskyscraper@gmail.com — not personal accounts.
- **skyscraperhq / skyscraperhq3 @ gmail.com handles** — Taken / suggested but unused. Live handle is hqskyscraper@gmail.com / Horizons123!. Do not re-propose.
- **Inventing 'Olga' as Wren's second-voice officer** — Auger is the tower-native role (src/tower/model_floors/claude_floor/auger.py). Helm is Ross-facing; Auger is Wren-facing; asymmetric contract is load-bearing.
- **£50/day live real-money trading** — Declined on principle — CLAUDE.md keeps real_money_live_trading_enabled FALSE. Tier-C flips require CLAUDE.md edit, never verbal. Only OANDA practice + Binance/stocks paper preview allowed.
- **Trusting qsb_floor_interior_master_registry.json over on-disk floors** — Master registry drifts. On-disk src/tower/floors/floor_N_*/ wins. Single source for floor labels is qsb_floor_name_map.json via qsb_hardware_floor.update_floor_name_map().

---
_Generated by `tools/qsb_wake_briefing.py`. Re-run any time. Sources: qsb_buffer_state.json, qsb_session_diary.md, qsb_f47_team_records.jsonl, qsb_claude_meta_letters.jsonl, qsb_abandoned_paths.jsonl._
