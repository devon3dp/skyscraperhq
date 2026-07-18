# WREN WAKE BRIEFING — 2026-07-17T10:00:01.390416Z

## To resume your last conversation
```
cd /vaults/nvme0/qsb_tower_v1
claude --resume 729a6533-fd3a-4c7b-a428-14a46a6a8bfe
```

_Read this every time you wake. It exists because Ross caught me re-pitching dead ideas across crashes._

## Tower vitals
- ✗ dashboard
- ✗ lumen
- ✗ vision
- ✗ heartbeat
- ✗ cloudflared
- ✗ qualify_loop

## Last snapshot
- ts: `2026-07-17T10:00:01.022040Z`
- alive_count: 0
- down: ['dashboard', 'lumen', 'vision', 'heartbeat', 'cloudflared', 'qualify', 'godot']
- f47_chat_tail_count: 20
- cli_chat_tail_count: 20
- unsigned_proposals: 60
- diary_last: - 18:47 UTC (2026-07-16) — PITSTOP `great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep`. Focus: Great Handover Priority Zero begun: Exec Concierge Blueprint v1 authored via Wren-persona-on-capable-model (Max/OAuth, paid key unset) after offline-Wren failed 3x (guessed sources, quit on path bug, FALSE 'revised' F47 stamp). v1 Claude-validated PASS (6 real sources, 0 phantoms, 0 secrets, unknowns marked), hashed 59f2deb3, versioned LATEST.txt, F47-stamped. Bill-side proof chain WAITING_ON_MAC (inbound SSH off). Architecture FROZEN.. Resume from data/registries/pitstops/pitstop_20260716T184721993847Z_great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep.md.
- last_decision: {'ts': '2026-07-17T09:59:51Z', 'kind': 'oanda_history_pull', 'operator': 'claude'}

## Diary tail
- 20:52 UTC (2026-07-12) — PITSTOP `physical-worker_live_cockpits___dashboard_hardening`. Focus: TP cockpit recovered; voice decision pending. Resume from data/registries/pitstops/pitstop_20260712T205234446441Z_physical-worker_live_cockpits___dashboard_hardening.md.
- 21:32 UTC (2026-07-12) — PITSTOP `physical-worker_competition-anchor_grounding___cockpit_dashb`. Focus: live grounding FAILED both workers; correction is PLAN-only pending Ross. Resume from data/registries/pitstops/pitstop_20260712T213213713488Z_physical-worker_competition-anchor_grounding___cockpit_dashb.md.
- 22:02 UTC (2026-07-12) — PITSTOP `physical-worker_grounding_repair___offline-autonomy`. Focus: TP-Pip PASS local anchor; Acer aged-out; routing not yet local-first. Resume from data/registries/pitstops/pitstop_20260712T220244129770Z_physical-worker_grounding_repair___offline-autonomy.md.
- 22:07 UTC (2026-07-12) — PITSTOP `federated_physical_nodes_blocked_on_acer_grounding`. Focus: gate stopped build; TP grounded, Acer competition anchor not proven. Resume from data/registries/pitstops/pitstop_20260712T220755263796Z_federated_physical_nodes_blocked_on_acer_grounding.md.
- 18:47 UTC (2026-07-15) — PITSTOP `pi_federation_dashboard___tp_acer_heartbeat___bill_admission`. Focus: SkyscraperHQ 24h Pi federation server: V3 touchscreen dashboard live; nodes online; Bill pending. Resume from data/registries/pitstops/pitstop_20260715T184733687394Z_pi_federation_dashboard___tp_acer_heartbeat___bill_admission.md.
- 14:41 UTC (2026-07-16) — PITSTOP `ssk_audit__caretaker_federation__2026-07-16`. Focus: SSK audit (read-only) + caretaker federation work; STOPPED for Ross review on SSK role decision. Resume from data/registries/pitstops/pitstop_20260716T144124309464Z_ssk_audit__caretaker_federation__2026-07-16.md.
- 15:21 UTC (2026-07-16) — PITSTOP `ssk_storage_vault__prepared_blocked_on_msi_pi_wifi__2026-07-`. Focus: SSK storage-only vault APPROVED + fully prepared (build script staged); execution BLOCKED on flaky MSI<->Pi wifi (SSH drops, HTTP ok). Stopped for Ross.. Resume from data/registries/pitstops/pitstop_20260716T152156741861Z_ssk_storage_vault__prepared_blocked_on_msi_pi_wifi__2026-07-.md.
- 18:47 UTC (2026-07-16) — PITSTOP `great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep`. Focus: Great Handover Priority Zero begun: Exec Concierge Blueprint v1 authored via Wren-persona-on-capable-model (Max/OAuth, paid key unset) after offline-Wren failed 3x (guessed sources, quit on path bug, FALSE 'revised' F47 stamp). v1 Claude-validated PASS (6 real sources, 0 phantoms, 0 secrets, unknowns marked), hashed 59f2deb3, versioned LATEST.txt, F47-stamped. Bill-side proof chain WAITING_ON_MAC (inbound SSH off). Architecture FROZEN.. Resume from data/registries/pitstops/pitstop_20260716T184721993847Z_great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep.md.

## Recent decisions (not heartbeat noise)
- `2026-07-17T09:51:16` triage_tick
- `2026-07-17T09:53:53` build_forward_idle
- `2026-07-17T09:55:26` hw_sample
- `2026-07-17T09:56:16` triage_tick
- `2026-07-17T09:59:51` oanda_history_pull

## Last letters (read in full before high-stakes action)
- `2026-07-16T14:41:24` gen=? · (no subject)
- `2026-07-16T15:21:56` gen=? · (no subject)
- `2026-07-16T18:47:21` gen=? · (no subject)

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
