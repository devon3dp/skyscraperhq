# QSB Tower Council Brief · regenerated 2026-07-18T14:29:51Z

This file is the SHARED context that both Wren (F46) and Hermes (F51) read
before every reply. Updated by the heartbeat tick (5-min cadence). If
something here is stale, re-run `tools/qsb_council_brief.py`.

## Today (2026-07-18)
- F41 OANDA cycles: 0
- F42 Binance cycles: 0
- F43 Alpaca cycles: 0
- Certified workers: 32

## Recent F47 events (last 15 non-noise)
- 2026-07-18T13:56:11  thermal_escalate  NORMAL -> WARN  
- 2026-07-18T13:56:53  assistant_reminder    memory_write_stale → pushed=True (msg 3826)
- 2026-07-18T13:56:54  assistant_reminder    diary_line_stale → pushed=True (msg 3827)
- 2026-07-18T13:56:54  assistant_reminder    backup_stale → pushed=True (msg 3828)
- 2026-07-18T13:57:01  wren_local_agent_session    sess wsess_b0 4 turns, 5 tool calls, 25.17s
- 2026-07-18T13:57:07  wren_evolution_board_task    [task_board] BOARD TASK — Wren designs their own Trading Annex

Description: Wren submits THEIR OWN annex design (self-designed, not by HQ).
- 2026-07-18T13:57:09  iquest_msg_from_wren  Evolution cycle 9: board_task — It appears that the design f  
- 2026-07-18T13:57:09  boardroom_announce  Evolution cycle 9: board_task — It appears that the design f  
- 2026-07-18T13:57:22  triage_tick  triage_alerts  Board Task Initiated: Wren's self-designed Trading Annex is now being constructed per their spec and integrated into the dashboard for Evolu
- 2026-07-18T13:59:41  classroom_evaluator_tick    Phase 2 classroom: 9 verdicts · {'promote_recommended': 3, 'watch_recommended': 6}
- 2026-07-18T13:59:51  team_sync_auto  30min_team_sync  
- 2026-07-18T14:01:08  wren_local_agent_session    sess wsess_5a 2 turns, 3 tool calls, 21.79s
- 2026-07-18T14:02:23  triage_tick  triage_alerts  No new OANDA fills or backlog items; thermal WARN persists from stalled processes but no critical action required pending Wren's self-design
- 2026-07-18T14:04:16  thermal_escalate  NORMAL -> WARN  
- 2026-07-18T14:06:38  thermal_escalate  NORMAL -> WARN  

## Recent diary lines (last 8)
- 22:02 UTC (2026-07-12) — PITSTOP `physical-worker_grounding_repair___offline-autonomy`. Focus: TP-Pip PASS local anchor; Acer aged-out; routing not yet local-first. Resume from data/registries/pitstops/pitstop_20260712T220244129770Z_physical-worker_grounding_repair___offline-autonomy.md.
- 22:07 UTC (2026-07-12) — PITSTOP `federated_physical_nodes_blocked_on_acer_grounding`. Focus: gate stopped build; TP grounded, Acer competition anchor not proven. Resume from data/registries/pitstops/pitstop_20260712T220755263796Z_federated_physical_nodes_blocked_on_acer_grounding.md.
- 18:47 UTC (2026-07-15) — PITSTOP `pi_federation_dashboard___tp_acer_heartbeat___bill_admission`. Focus: SkyscraperHQ 24h Pi federation server: V3 touchscreen dashboard live; nodes online; Bill pending. Resume from data/registries/pitstops/pitstop_20260715T184733687394Z_pi_federation_dashboard___tp_acer_heartbeat___bill_admission.md.
- 14:41 UTC (2026-07-16) — PITSTOP `ssk_audit__caretaker_federation__2026-07-16`. Focus: SSK audit (read-only) + caretaker federation work; STOPPED for Ross review on SSK role decision. Resume from data/registries/pitstops/pitstop_20260716T144124309464Z_ssk_audit__caretaker_federation__2026-07-16.md.
- 15:21 UTC (2026-07-16) — PITSTOP `ssk_storage_vault__prepared_blocked_on_msi_pi_wifi__2026-07-`. Focus: SSK storage-only vault APPROVED + fully prepared (build script staged); execution BLOCKED on flaky MSI<->Pi wifi (SSH drops, HTTP ok). Stopped for Ross.. Resume from data/registries/pitstops/pitstop_20260716T152156741861Z_ssk_storage_vault__prepared_blocked_on_msi_pi_wifi__2026-07-.md.
16:11 UTC (2026-07-16) — F47 master NUL-corruption repair. 4 lines (31278/56392/58926/61909) had power-loss zero-fill prefixes; stripped leading NULs (lossless, all recovered to valid JSON). Snapshots had been aborting since 07-07; now green — qsb_f47_2026-07-16.jsonl (63188 rows). Backup: master.bak_20260716T161001Z_nulrepair.
- 18:47 UTC (2026-07-16) — PITSTOP `great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep`. Focus: Great Handover Priority Zero begun: Exec Concierge Blueprint v1 authored via Wren-persona-on-capable-model (Max/OAuth, paid key unset) after offline-Wren failed 3x (guessed sources, quit on path bug, FALSE 'revised' F47 stamp). v1 Claude-validated PASS (6 real sources, 0 phantoms, 0 secrets, unknowns marked), hashed 59f2deb3, versioned LATEST.txt, F47-stamped. Bill-side proof chain WAITING_ON_MAC (inbound SSH off). Architecture FROZEN.. Resume from data/registries/pitstops/pitstop_20260716T184721993847Z_great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep.md.
- 10:00 UTC (2026-07-17) — PITSTOP `wren_floor46_electron_dashboard_cobuild_with_wren`. Focus: Floor 46 GPU-Governor 3D Electron dashboard, co-designed WITH Wren (she decides+signs off, Claude implements). Live under systemd --user. 3 co-improvement rounds all signed off.. Resume from data/registries/pitstops/pitstop_20260717T100000634539Z_wren_floor46_electron_dashboard_cobuild_with_wren.md.

## Last 5 pitstops
- pitstop_20260717T100000634539Z_wren_floor46_electron_dashboard_cobuild_with_wren.md
- pitstop_20260716T184721993847Z_great_handover_blueprint_v1__cage_smoke_blocked__f47_nul_rep.md
- pitstop_20260716T152156741861Z_ssk_storage_vault__prepared_blocked_on_msi_pi_wifi__2026-07-.md
- pitstop_20260716T144124309464Z_ssk_audit__caretaker_federation__2026-07-16.md
- pitstop_20260715T184733687394Z_pi_federation_dashboard___tp_acer_heartbeat___bill_admission.md

## Permanent constraints (per memory)
- Ross lives on a boat off-grid (lithium batteries, no wall power)
- 3-CEO board: Ross (concept) + Wren (bench) + Claude (helm)
- Hermes joined as non-voting advisor 2026-06-20
- **iquest-coder (40B Llama, completion-only)** joined boardroom F51 as
  full team member 2026-06-21 (Ross override on 2-2 split). Code-review
  specialist; catches gotchas peers miss (e.g. daemon return-shape catch
  that saved a SAFETY_DENY-adjacent edit 2026-06-21).
- **hermes3:70b LIVE** in Ollama 2026-06-21 — Hermes-smart-mode for hard
  council calls; hermes3:8b stays as fast battle ringmaster.
- Real-money execution gates ALL locked false (advisory only)
- OANDA practice trading is the ONE runtime exception
- Every job needs proof-before-signoff + team-dispatch before claiming done

## Tower architecture (NEW 2026-06-21 — anti-stale-grounding section)
These are CITED FACTS. Use them when asked about the cockpit / Godot / 3D /
F46 / F47 / rendering. The old PyQt5/QGraphicsScene panel is RETIRED.

- **Cockpit3D (browser)** — Three.js scene at `http://127.0.0.1:8765/cockpit3d/`.
  Has walkable F46 (Wren's Bench) + F47 (Claude Embassy) interiors, supertonic
  TTS voice playback, AI battle viewer, kernel chat sidebar.
- **Godot native cockpit** — `/home/ross/qsb_godot_native_cockpit/` (Godot 4.7
  Vulkan, Forward+ on RTX 5070 Ti). Main.tscn is the runtime scene. Has tower
  with rainbow floor stack, F46 walkable, F47 walkable (Claude Embassy with
  25 rooms via /api/floor_rooms/47), safety envelope panel, event ticker.
- **F46 Wren's Bench** — 50×50 walkable interior + Wren chat panel
  (browser/Godot both). Header verified visually 2026-06-20.
- **F47 Claude Embassy** — walkable interior, helix display centred, embassy
  brass + Wren green palette, 25 rooms placed by /api/floor_rooms/47 endpoint.
- **Mouse mode in walk** — was MOUSE_MODE_CAPTURED (broke mouse feel),
  fixed 2026-06-21 to MOUSE_MODE_CONFINED. Cursor visible + clamped to window.
- **Floor rooms data** — 168 / 169 floors now have rooms/*.json (mass fitout
  2026-06-21 via qsb_floor_rooms_generate.py --all-missing).
- **Models live in Ollama** (2026-06-21):
  qwen2.5:7b (Wren-fast) · qwen2.5:32b (Wren-smart, NEW) · hermes3:8b
  (Hermes) · hermes3:70b (pulling, ETA ~3h) · iquest-coder:40b · qwen3.5:9b
  · llava:7b · others.
- **F41 paper-simulator** — was 0/595 wins from bid-ask spread bleed (entry
  ASK, close BID). Mid-price fix shipped 2026-06-21 + daemons restarted.
  F41 trader_memory/ backfilled (16 files). 10-min replay timer active.

## Known facts (CORRECTED 2026-06-21 afternoon)
- **TikTok handle**: NOW `@hqskyscraper` (Ross manually changed it via PC
  web after Claude's earlier ADB attempts kept failing on Galaxy due to no
  internet). Display name: "Skyscraper Hq". Bio still empty, pronoun / link
  still unset — to be set next.

If a question goes beyond these facts, say so honestly. Don't invent.

## How to use this brief (Wren / Hermes)
- Cite the brief when answering ("Per today's brief, F43 is at X cycles…")
- If asked about something NOT in the brief, say so honestly — don't
  hallucinate. (Hermes: this means YOU specifically.)
- If you see something here that's WRONG, flag it on the council JSONL
  (`qsb_three_way_council.jsonl`).

## Provider helpers (NEW 2026-06-21 — advisor consultations available)
You are NOT alone. Two external advisor models can be consulted on hard
questions: **OpenAI gpt-4o-mini** and **DeepSeek deepseek-chat**. They are
decorators / second-opinion givers — NOT architects, not floor owners, not
your replacement. They're tools you can ask for help when:
- you're uncertain about a fact you can't verify from this brief
- you want an adversarial sanity check on your own reasoning
- the question is harder than 7-8B parameters can handle confidently
- you'd say "I don't know" otherwise

How to request help: in your reply, end with one line:
    `CONSULT_REQUEST: <openai|deepseek> · <one-line question>`
Claude routes the request (via tools/qsb_consult_external.py), brings back
the advisor's answer, and re-dispatches to you for synthesis. You remain
the principal — providers decorate your brief, they don't replace it.

Bounds: $1.00/day across both providers combined. Don't request on greetings
or trivial lookups. Only when YOU as Wren/Hermes feel the question exceeds
your confident reach.
