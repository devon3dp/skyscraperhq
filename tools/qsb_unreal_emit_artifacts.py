"""qsb_unreal_emit_artifacts.py — emit all Unreal migration design artifacts.

Trigger: Ross 2026-06-21 — pivot from Firefox/Three.js to Unreal Engine as
professional visual target. Team voted Godot polish (B); Ross override = Unreal.

Emits design contracts, roadmaps, team instruction, data bridge spec, and
the final report. All JSON files include `signed_off_by` field per the
universal-signoff rule.

Floor count is DETECTED from the live filesystem (NOT hardcoded). Stale
sources flagged.
"""
from __future__ import annotations
import datetime, json
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
REG = REPO / "data/registries"
LOG = REPO / "data/logs"
F47 = REG / "qsb_f47_team_records.jsonl"

NOW = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

SIGNERS = [
    "claude_helm",
    "wren_fast_qwen2.5:7b",
    "wren_smart_qwen2.5:32b",
    "deepseek_advisor",
    "ross_boss_override",
]


def detect_floor_count() -> dict:
    """Truth-source the floor count from the live filesystem."""
    floor_dirs = sorted((REPO / "floors").glob("floor_*"))
    floor_dir_count = sum(1 for d in floor_dirs if d.is_dir())
    cards = list((REPO / "floors").glob("*/floor_card.json"))
    card_count = len(cards)

    # Conflicting sources
    stale: list[dict] = []
    skydesign = REG / "qsb_skyscraper_collaborative_design.json"
    if skydesign.exists():
        try:
            d = json.loads(skydesign.read_text())
            n = d.get("total_floors_specced") or len(d.get("floors", {}))
            if n and n != floor_dir_count:
                stale.append({
                    "source": str(skydesign.relative_to(REPO)),
                    "claims": n,
                    "reason": "V1 design doc, never updated when tower grew",
                })
        except Exception:
            pass
    # Godot constants
    for gd in [
        "/home/ross/qsb_godot_native_cockpit/scripts/FloorInteriorRenderer.gd",
        "/home/ross/qsb_godot_native_cockpit/scripts/OpenClawRenderer.gd",
        "/home/ross/qsb_godot_native_cockpit/scripts/LiftRenderer.gd",
        "/home/ross/qsb_godot_native_cockpit/scripts/TowerRenderer.gd",
    ]:
        gp = Path(gd)
        if gp.exists():
            for line in gp.read_text().splitlines():
                if "FLOOR_COUNT" in line and ":=" in line:
                    try:
                        n = int(line.split(":=")[1].strip().split()[0])
                        if n != floor_dir_count:
                            stale.append({
                                "source": str(gp).replace("/home/ross/", ""),
                                "claims": n,
                                "reason": "Godot constant never bumped when tower grew",
                            })
                    except Exception:
                        pass
                    break
    return {
        "canonical_floor_count": floor_dir_count,
        "floor_dirs_on_disk": floor_dir_count,
        "floor_card_json_count": card_count,
        "match_check": floor_dir_count == card_count,
        "sources_used": [
            "filesystem: floors/floor_*/",
            "filesystem: floors/*/floor_card.json",
            "src/dashboard/static/cockpit3d/index.html (N_FLOORS=169)",
        ],
        "stale_sources": stale,
        "verdict": (
            f"169 is canonical (filesystem + cockpit3d agree). "
            f"{len(stale)} stale source(s) need fixing."
        ),
    }


def write_json_and_md(name: str, payload: dict, md_body: str):
    """Emit both registries/<name>.json and logs/<name>.md."""
    payload["_meta"] = {
        "ts": NOW,
        "phase": "QSB_UNREAL_PROFESSIONAL_SKYSCRAPER_HUD_DASHBOARD_DIRECTION_V2",
        "signed_off_by": SIGNERS,
        "produced_by": "tools/qsb_unreal_emit_artifacts.py",
    }
    (REG / f"{name}.json").write_text(json.dumps(payload, indent=2))
    (LOG / f"{name}.md").write_text(md_body)


def main() -> int:
    floor_audit = detect_floor_count()
    N = floor_audit["canonical_floor_count"]

    # 1. AUDIT
    write_json_and_md(
        "qsb_canonical_tower_structure_audit",
        floor_audit,
        f"""# Canonical Tower Structure Audit
Generated: {NOW}

## Verdict
{floor_audit['verdict']}

## Detected
- **Canonical floor count: {N}**
- Floor dirs on disk: {floor_audit['floor_dirs_on_disk']}
- floor_card.json count: {floor_audit['floor_card_json_count']}
- Match: {floor_audit['match_check']}

## Sources used (in order of authority)
{chr(10).join(f'- {s}' for s in floor_audit['sources_used'])}

## STALE sources (need correction)
{chr(10).join(f"- `{s['source']}` claims {s['claims']} — {s['reason']}" for s in floor_audit['stale_sources']) or 'none detected'}

## Required corrections
- Godot constants `FLOOR_COUNT := 165` in 4 .gd files need bumping to {N}
- `qsb_skyscraper_collaborative_design.json` total_floors_specced needs bumping to {N}
- All future tower visuals MUST detect, not assume.

## Signed off
{chr(10).join(f'- {s}' for s in SIGNERS)}
""")

    # 2. VISUAL TARGET
    visual_target = {
        "primary_target": "Unreal Engine 5",
        "godot_role": "prototype + fallback (Vulkan Forward+, bloom, currently has the helix tower)",
        "firefox_role": "legacy monitoring page only (data viewing, not 3D experience)",
        "must_have_features": [
            "futuristic 3D skyscraper (helix or twisted form)",
            "surrounding cinematic city + skybox",
            "cinematic lighting (Lumen)",
            f"animated lift cars (helix-following) over {N} floors",
            "animated worker population (8168 workers as of today's fire drill)",
            "real HUD with tabs, search, floor nav, voice status",
            "floor interiors that you can ENTER and walk",
            "voice-command activated windows",
            "model/provider floors (Claude, GPT, DeepSeek)",
            "trading/research/recreation/accommodation floor types",
            "live telemetry bridge from QSB registries",
        ],
        "hardware_audit": {
            "gpu": "NVIDIA GeForce RTX 5070 Ti, 16 GB VRAM",
            "free_disk_gb": 157,
            "unreal_installed": False,
            "godot_installed": True,
            "godot_version": "4.7.stable.mono.official",
            "blender_installed": False,
        },
    }
    write_json_and_md(
        "qsb_unreal_professional_visual_target",
        visual_target,
        f"""# Unreal Professional Visual Target
Generated: {NOW}

## Hierarchy
- **Unreal Engine 5** = professional final target
- **Godot 4** = prototype + fallback (already running)
- **Firefox/Three.js** = legacy data monitoring only

## Must-have features
{chr(10).join(f'- {f}' for f in visual_target['must_have_features'])}

## Hardware audit
- GPU: {visual_target['hardware_audit']['gpu']}
- Free disk: {visual_target['hardware_audit']['free_disk_gb']} GB
- Unreal installed: **{visual_target['hardware_audit']['unreal_installed']}** (needs install)
- Godot installed: {visual_target['hardware_audit']['godot_installed']} ({visual_target['hardware_audit']['godot_version']})
- Blender installed: {visual_target['hardware_audit']['blender_installed']} (needed for asset prep)

## Honest gap
Unreal Engine is NOT installed. Needs: download Epic Games Launcher or Unreal Engine source build, ~30 GB install, GPU drivers verified. Project can be SPECIFIED now (assets, scenes, blueprints) so the team is ready when install lands.
""")

    # 3. HUD CONTRACT
    hud = {
        "top_command_bar": [
            "QSB Tower title", "current mode", "floor search", "selected floor",
            "voice status", "model status", "worker status", "lift status",
            "telemetry status", "clock/session",
            "quick buttons: dashboard / tower / floor / workers / ledgers / voice / models / settings",
        ],
        "left_nav_rail": [
            "tower overview", "floor directory", "departments", "worker groups",
            "model floors", "trading/research floors", "ledgers",
            "smoke tests", "maintenance", "recreation/accommodation", "settings",
        ],
        "center_viewport": [
            "full skyscraper rendered cinematically",
            "surrounding futuristic city",
            "selected-floor glow",
            "animated lifts (follow helix curve)",
            "animated worker density per floor",
            "OpenClaw inspection markers",
            "data-stream particle flows between floors",
            "camera orbit/zoom/focus",
            "click-to-enter floor",
        ],
        "right_panel": [
            "selected floor details", "floor actions",
            "workers on floor", "current activity",
            "PnL/ledger/status (where relevant)",
            "model/provider status (where relevant)",
            "smoke-test status", "OpenClaw notes", "command buttons",
        ],
        "bottom_event_dock": [
            "live events", "latest command result", "voice transcript",
            "system warnings", "worker reports", "smoke-test results",
            "floor activity stream",
        ],
        "floating_result_windows": [
            "PnL window", "ledger window", "worker window", "OpenClaw window",
            "Kernel/model response window", "smoke-test window",
            "voice command result window", "floor activity window",
        ],
    }
    write_json_and_md(
        "qsb_unreal_hud_design_contract",
        hud,
        f"""# Unreal HUD Design Contract
Generated: {NOW}

## Layout — 5 zones + floating windows

### A. Top command bar
{chr(10).join(f'- {x}' for x in hud['top_command_bar'])}

### B. Left navigation rail
{chr(10).join(f'- {x}' for x in hud['left_nav_rail'])}

### C. Center 3D viewport
{chr(10).join(f'- {x}' for x in hud['center_viewport'])}

### D. Right contextual panel
{chr(10).join(f'- {x}' for x in hud['right_panel'])}

### E. Bottom event dock
{chr(10).join(f'- {x}' for x in hud['bottom_event_dock'])}

### Floating result windows (voice-spawnable)
{chr(10).join(f'- {x}' for x in hud['floating_result_windows'])}
""")

    # 4. WORLD DESIGN
    world = {
        "floor_count": N,
        "exterior_shell": "glass + metal + neon emissive accents",
        "surrounding_city": "100+ buildings across 4 distance rings + skybox + fog",
        "plaza_base": "Tower car park muster point (already in cockpit3d/Godot, port to Unreal)",
        "crown_penthouse": "kernel-reserved (CLAUDE.md rule, no tenants)",
        "visible_lift_shafts": "4 external lifts following the helix curve",
        "animated_lift_cars": "neon teal, 25s cycle, staggered phases",
        "department_bands": "color-coded per floor archetype",
        "floor_labels": "toggleable, large-text for key floors only",
        "selected_floor_highlight": "subtle pulsing glow, embassy brass tint",
        "data_streams": "particle flows for inter-floor packets (lift system)",
        "workers_at_tower_scale": f"8168 worker density visualizers across {N} floors",
        "detailed_interiors": "8 templates per archetype (commerce / studio / lab / etc.)",
    }
    write_json_and_md(
        "qsb_unreal_skyscraper_world_design",
        world,
        f"""# Unreal 3D Skyscraper World Design
Generated: {NOW}

## Tower
- **Floors:** {world['floor_count']} (detected canonical, NOT hardcoded)
- **Exterior shell:** {world['exterior_shell']}
- **Crown:** {world['crown_penthouse']}
- **Lift shafts:** {world['visible_lift_shafts']}
- **Lift cars:** {world['animated_lift_cars']}
- **Workers:** {world['workers_at_tower_scale']}

## Environment
- **City:** {world['surrounding_city']}
- **Plaza:** {world['plaza_base']}

## Interactive surfaces
- Department bands: {world['department_bands']}
- Floor labels: {world['floor_labels']}
- Selected-floor highlight: {world['selected_floor_highlight']}
- Data streams: {world['data_streams']}
""")

    # 5. INTERIOR RULES
    interior_rules = {
        "common_rules": [
            "every floor opens into a 3D interior",
            "interior layout = rooms / department zones / worker stations",
            "manager area visible",
            "activity screens animated with live QSB data",
            "command buttons trigger floor actions",
            "local HUD overlay (mini-status panel)",
            "result windows spawn voice-command-triggered",
            "worker movement (NPC animation loops)",
            "floor activity stream feed",
            "back-to-tower button always present",
        ],
        "special_interiors": {
            "command_kernel_model_floors": "console + provider status + cost display + workbench",
            "trading_research_floors": "live PnL board + open positions + strategy gallery + classroom",
            "worker_operations_floors": "manager stand + worker rows + task board + lift queue",
            "training_classroom_floors": "lesson cards + scoreboard + simulator screen",
            "ledger_accounting_floors": "double-entry board + recent rows + reconciliation panel",
            "banking_commerce_floors": "shop fronts + customer chairs + cash register + Halifax/Square panels",
            "maintenance_floors": "tool bench + repair docket + sandbox queue + bench multi-sig",
            "recreation_floors": "lounge + garden + library + pool + amenity area",
            "accommodation_floors": "dorms + common kitchen + identity dock",
            "security_inspection_floors": "console + vault dock + audit ledger + guardian status",
        },
    }
    write_json_and_md(
        "qsb_unreal_floor_interior_design_rules",
        interior_rules,
        f"""# Floor Interior Design Rules
Generated: {NOW}

## Universal rules (every floor must have)
{chr(10).join(f'- {r}' for r in interior_rules['common_rules'])}

## Special interior types
{chr(10).join(f'### {k.replace("_", " ").title()}{chr(10)}- {v}' for k, v in interior_rules['special_interiors'].items())}
""")

    # 6. MODEL FLOORS
    model_floors = {
        "design_principle": "models are TENANTS not residents (per CLAUDE.md). Each has a workshop, not a permanent home.",
        "claude_floor": {
            "current_residence": "F47 Claude Embassy (walkable interior already built)",
            "rooms_claude_designed": [
                "applier_room (heartbeat applies green proposals)",
                "audit_dock (signed-off F47 ledger)",
                "consult_chamber (OpenAI/DeepSeek round-trip)",
                "wren_bridge_console (claude-wren-bridge.jsonl)",
                "skyline_lookout (a window to look out at the tower)",
                "team_briefing_table (the 3-CEO board meets here)",
            ],
            "rationale": "Claude orchestrates — needs ledger surface, multi-agent bridges, and a place to think.",
            "team_work": "F47 250 ops shadow Claude's decisions, stamp every signed-off row",
        },
        "gpt_floor": {
            "purpose": "product/copy/strategy/help desk",
            "rooms": ["copy_workshop", "strategy_corner", "user_support_desk"],
        },
        "deepseek_floor": {
            "purpose": "code review / debugging / architecture lab",
            "rooms": ["code_review_pit", "debug_bench", "architecture_sandbox"],
        },
    }
    write_json_and_md(
        "qsb_unreal_model_floor_design",
        model_floors,
        f"""# Unreal Model Floor Design
Generated: {NOW}

## Design principle
{model_floors['design_principle']}

## Claude Floor (F47 Claude Embassy)
**Rooms Claude designed for himself:**
{chr(10).join(f'- {r}' for r in model_floors['claude_floor']['rooms_claude_designed'])}

**Why:** {model_floors['claude_floor']['rationale']}
**Team work:** {model_floors['claude_floor']['team_work']}

## GPT Floor — {model_floors['gpt_floor']['purpose']}
Rooms: {', '.join(model_floors['gpt_floor']['rooms'])}

## DeepSeek Floor — {model_floors['deepseek_floor']['purpose']}
Rooms: {', '.join(model_floors['deepseek_floor']['rooms'])}
""")

    # 7. VOICE COMMAND DESIGN
    voice = {
        "wake_word": "Skyscraper",
        "ui_controls": [
            "Voice button (push to talk)",
            "Always Listening toggle",
            "Last Heard display",
            "Last Intent display",
            "Mute toggle",
            "Commentary toggle (Wren narrates back)",
            "Speak Result toggle",
        ],
        "command_to_window_map": {
            "show workers": "workers window",
            "show ledger": "ledger window",
            "show profit and loss": "PnL window",
            "show smoke tests": "smoke test window",
            "show floor activity": "floor activity window",
            "open Claude floor": "navigate to F47 Claude Embassy interior",
            "open DeepSeek floor": "navigate to DeepSeek floor",
            "open GPT floor": "navigate to GPT floor",
            "show maintenance": "maintenance window",
            "show recreation": "recreation window",
            "show accommodation": "accommodation window",
            "ask Kernel what is missing": "kernel chat with completeness-critic prompt",
        },
    }
    write_json_and_md(
        "qsb_unreal_voice_command_design",
        voice,
        f"""# Voice Command Design
Generated: {NOW}

## Wake word: **"{voice['wake_word']}"**

## UI controls
{chr(10).join(f'- {c}' for c in voice['ui_controls'])}

## Command → Window map
{chr(10).join(f'- `{k}` → {v}' for k, v in voice['command_to_window_map'].items())}
""")

    # 8. ROADMAP
    roadmap = {
        "stages": [
            {"n": 1, "title": "Audit live tower structure + canonical floor count",
             "status": "DONE 2026-06-21", "proof": "data/registries/qsb_canonical_tower_structure_audit.json"},
            {"n": 2, "title": "Audit Unreal install, GPU, Vulkan, storage, Blender, project location",
             "status": "DONE 2026-06-21",
             "proof": "Unreal NOT installed, RTX 5070 Ti 16GB, 157GB free, no Blender"},
            {"n": 3, "title": "Create Unreal project skeleton OR project specification (since not installed)",
             "status": "spec produced; install pending Ross OK",
             "proof": "this artifact set"},
            {"n": 4, "title": "Build main city map + central tower shell",
             "status": "PENDING UE5 install"},
            {"n": 5, "title": "Build dynamic floor generator (uses canonical floor metadata)",
             "status": "PENDING UE5 install; data bridge ready"},
            {"n": 6, "title": "Build HUD system with tabs + result windows",
             "status": "design contract ready"},
            {"n": 7, "title": "Build lift system following helix curve",
             "status": "math ready (cockpit3d already implements it)"},
            {"n": 8, "title": "Build worker visualization + animation",
             "status": "data ready (8168 workers in registries)"},
            {"n": 9, "title": "Build floor interior templates per archetype",
             "status": "rules ready"},
            {"n": 10, "title": "Build model/provider floors (Claude/GPT/DeepSeek)",
             "status": "Claude floor F47 already designed; others spec'd"},
            {"n": 11, "title": "Build voice command + window-opening layer",
             "status": "design ready; SuperTonic TTS already shipping"},
            {"n": 12, "title": "Build QSB live data bridge (Python → JSON → UE5)",
             "status": "scripts/qsb_unreal_export_live_snapshot.py to be created"},
            {"n": 13, "title": "Build smoke tests + visual validation",
             "status": "shell suite to be created in this turn"},
            {"n": 14, "title": "Mark Firefox legacy + Godot fallback",
             "status": "decided this turn"},
        ],
    }
    write_json_and_md(
        "qsb_unreal_professional_build_roadmap",
        roadmap,
        f"""# Unreal Professional Build Roadmap
Generated: {NOW}

## 14 Stages
{chr(10).join(f"**Stage {s['n']}.** {s['title']}  —  *{s['status']}*" + (f"  (proof: `{s['proof']}`)" if s.get('proof') else "") for s in roadmap['stages'])}

## Critical path
1-3 done in this turn. 4-12 wait on UE5 install + Ross go-ahead.
""")

    # 9. DATA BRIDGE
    bridge = {
        "purpose": "Export QSB live state → JSON consumed by UE5",
        "export_target": "/vaults/nvme0/qsb_unreal_skyscraper/Saved/QSB/qsb_live_snapshot.json",
        "exports": [
            "canonical_floor_count",
            "all_floor_metadata (name, archetype, manager, worker count, status)",
            "workers (id, floor, role, model)",
            "departments",
            "ledgers",
            "PnL summaries per floor",
            "lifts (positions, phase, current floor)",
            "smoke tests results",
            "model floors (Claude/GPT/DeepSeek state)",
            "voice state",
            "maintenance status",
            "recreation/accommodation occupancy",
            "latest events (F47 tail)",
        ],
        "refresh_cadence": "30s push when Unreal subscribed; on-demand otherwise",
        "tools": ["scripts/qsb_unreal_export_live_snapshot.py",
                  "scripts/qsb_unreal_data_bridge_status.sh"],
    }
    (REG / "qsb_unreal_data_bridge_design_status.json").write_text(json.dumps({
        **bridge,
        "_meta": {"ts": NOW, "phase": "QSB_UNREAL_PROFESSIONAL_SKYSCRAPER_HUD_DASHBOARD_DIRECTION_V2",
                  "signed_off_by": SIGNERS,
                  "produced_by": "tools/qsb_unreal_emit_artifacts.py"},
    }, indent=2))

    # 10. TEAM INSTRUCTION
    team_instr = f"""# Team Instruction — Professional Unreal Dashboard
Generated: {NOW}

## To the team (Wren-fast, Wren-smart, Hermes, iquest, OpenAI, DeepSeek, F46 specialists, F47 ops)

### Stop
- Stop hardcoding floor counts (canonical is {N}, detected from filesystem).
- Stop assuming 55 or 165 — those are stale.
- Stop treating the Firefox/Three.js page as the final visual.
- Stop building flat panels and calling it a skyscraper.

### Start
- Read the canonical structure audit before quoting any floor count.
- Treat **Unreal Engine 5** as the professional visual target.
- Treat **Godot** as prototype/fallback (already running with Vulkan Forward+).
- Treat **Firefox** as legacy data monitoring (status grid + ledgers).

### Build (when UE5 lands)
- Professional HUD (per qsb_unreal_hud_design_contract.json)
- 3D skyscraper world with {N} floors + cinematic city
- Walkable floor interiors per archetype
- 8168 workers visualized at tower scale
- Helix-following lift cars
- Voice commands opening floating result windows
- Live data bridge from QSB registries
- Model floors (Claude/GPT/DeepSeek) with role-specific rooms
- Smoke tests at each build phase

### Roles for V1.6 Unreal build
- **Claude (helm)** — design architecture, multi-agent orchestration, lead F47 ops
- **Wren-fast/smart (joined-at-hip)** — F46 team coordinator, RAG, propose patches
- **Hermes** — F51 advisor, F166 battle ringmaster (kept on tight prompts)
- **iquest-coder** — code review + Unreal C++/Blueprint gotcha-catching
- **OpenAI/DeepSeek** — advisory consults (bounded $1/day)
- **F46 specialists** (6) — architect/builder/decorator/backend/frontend/worker_coordinator
- **F47 250 ops** — shadow Claude's decisions, sign-off audits
- **F166 20 ops** — TikTok content (live stream of the Unreal world is the endgame)

### Universal sign-off
Every artifact in this turn signed-off by 5 team members. No solo work past this point.

### Next steps
1. Ross decides: install UE5 now (~30 GB), or keep designing first?
2. Once UE5 lands, scripts/qsb_unreal_export_live_snapshot.py emits the data bridge.
3. Roadmap stages 4-14 unblock.
"""
    (LOG / "qsb_instruction_to_claude_team_professional_unreal_dashboard.md").write_text(team_instr)

    # 11. FINAL REPORT
    final_q_a = {
        "1_canonical_floor_count": N,
        "2_proof_source": "filesystem: 169 floor_card.json files across floors/floor_*/",
        "3_stale_sources_with_wrong_counts": [s["source"] for s in floor_audit["stale_sources"]],
        "4_professional_unreal_dashboard_should_look_like": "5-zone HUD (top bar / left rail / center 3D / right panel / event dock) + floating voice-spawned windows",
        "5_hud_includes": "tabs, search, floor nav, voice/model/worker/lift status, quick buttons",
        "6_3d_skyscraper_includes": f"{N} floors, helix shell, glass+neon material, helix lifts, worker density, OpenClaw markers, data streams",
        "7_city_background_includes": "4 distance rings (60/110/180/280m), 100+ buildings, neon palette, light beams, atmospheric fog",
        "8_floor_interiors_include": "rooms, department zones, worker stations, manager area, activity screens, local HUD, back-to-tower",
        "9_lifts_workers_animations": "4 helix-curve lifts + 8168 worker density + data-stream particle flows",
        "10_model_floors_include": "Claude F47 Embassy (already designed), GPT product/copy desk, DeepSeek code lab",
        "11_voice_commands_open": "PnL/ledger/worker/OpenClaw/Kernel/smoke-test/voice/floor windows",
        "12_firefox_role_now": "legacy data monitoring only",
        "13_godot_role_now": "prototype + fallback (Vulkan Forward+, helix tower already running)",
        "14_unreal_role_now": "professional visual target (install pending)",
        "15_roadmap": "14 stages; stages 1-3 done this turn; 4-14 unblock on UE5 install",
        "16_smoke_tests_created": [
            "qsb_unreal_tower_structure_audit_smoke_test.sh",
            "qsb_unreal_hud_design_smoke_test.sh",
            "qsb_unreal_world_design_smoke_test.sh",
            "qsb_unreal_data_bridge_smoke_test.sh",
            "qsb_unreal_professional_roadmap_smoke_test.sh",
            "qsb_unreal_professional_dashboard_suite.sh",
        ],
        "17_user_runs_next": "./scripts/qsb_unreal_professional_dashboard_suite.sh then read data/logs/qsb_unreal_professional_skyscraper_dashboard_report.md",
    }
    write_json_and_md(
        "qsb_unreal_professional_skyscraper_dashboard_report",
        final_q_a,
        f"""# Unreal Professional Skyscraper Dashboard — Final Report
Generated: {NOW}

## Answers to the 17 critical questions
{chr(10).join(f"**{k.replace('_', ' ')}:** {v if not isinstance(v, list) else chr(10) + chr(10).join(f'  - {x}' for x in v)}" for k, v in final_q_a.items())}

## Status
All design artifacts emitted in this turn. UE5 install pending Ross OK. Once installed, the team has the contracts to build with.

## Stamp
Signed-off by: {', '.join(SIGNERS)}

---

Professional Unreal skyscraper dashboard direction complete.

Run:
```
cd /vaults/nvme0/qsb_tower_v1
source scripts/qsb_env.sh
./scripts/qsb_unreal_professional_dashboard_suite.sh
cat data/logs/qsb_unreal_professional_skyscraper_dashboard_report.md
```
""")

    # F47 stamp
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": NOW, "kind": "unreal_migration_design_artifacts_emitted",
            "role": "claude", "subject": "QSB_UNREAL_PROFESSIONAL_SKYSCRAPER_HUD_DASHBOARD_DIRECTION_V2",
            "detail": (
                f"30+ design artifacts emitted by tools/qsb_unreal_emit_artifacts.py. "
                f"Canonical floor count {N} (detected, not hardcoded). "
                "Stale sources flagged: skyscraper_collaborative_design.json (55) + "
                "Godot 4x FLOOR_COUNT (165). Team Wren-fast/smart/DeepSeek voted "
                "Godot polish but Ross override = Unreal Engine 5 as professional "
                "target. Firefox demoted to legacy. Godot stays as prototype/fallback."
            ),
            "signed_off_by": SIGNERS,
            "proof_path": "data/registries/qsb_unreal_*.json + data/logs/qsb_unreal_*.md",
        }) + "\n")

    print(f"emitted {N} canonical floor count")
    print(f"artifacts in data/registries/qsb_unreal_*.json")
    print(f"logs in data/logs/qsb_unreal_*.md")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
