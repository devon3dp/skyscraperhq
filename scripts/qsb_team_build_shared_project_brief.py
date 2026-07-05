#!/usr/bin/env python3
"""Build the canonical shared project brief that every team member reads first.

Output:
  data/team_memory/shared/shared_project_brief.md
  data/team_memory/shared/shared_project_state.json
"""
from __future__ import annotations
import json
import subprocess
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SHARED = ROOT / "data/team_memory/shared"
SHARED.mkdir(parents=True, exist_ok=True)

TS = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_read(p: Path, head_lines: int = 0) -> str:
    try:
        if not p.exists():
            return ""
        text = p.read_text()
        if head_lines:
            text = "\n".join(text.splitlines()[:head_lines])
        return text
    except Exception as e:
        return f"<read-error: {e}>"


def safe_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


# Detect canonical floor count (not hardcoded)
canon_path = ROOT / "data/registries/qsb_canonical_tower_structure_latest.json"
canon = safe_json(canon_path)
floor_count = canon.get("canonical_floor_count", "unknown")

# Roster
roster = safe_json(ROOT / "data/registries/qsb_team_model_roster_latest.json")

# Fleet
def count_procs(pattern: str) -> int:
    r = subprocess.run(["bash", "-c", f"ps -eo cmd ww | grep -E '{pattern}' | grep -v grep | wc -l"],
                       capture_output=True, text=True, timeout=5)
    try:
        return int(r.stdout.strip())
    except Exception:
        return -1

fleet = {
    "f41_oanda": count_procs(r"qsb_belief_driven_trader.*--venue oanda"),
    "f42_binance": count_procs(r"qsb_belief_driven_trader.*--venue binance"),
    "f43_alpaca": count_procs(r"qsb_belief_driven_trader.*--venue alpaca"),
    "ensembles": count_procs(r"qsb_ensemble_coordinator"),
    "bus": count_procs(r"qsb_event_bus\.py"),
    "belief_updater": count_procs(r"qsb_belief_updater"),
    "regime_detector": count_procs(r"qsb_regime_detector"),
    "streams": count_procs(r"qsb_f4[123]_(binance|oanda|alpaca)_stream"),
}

# Dashboards
def http_code(url: str) -> str:
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "3", url],
                       capture_output=True, text=True, timeout=6)
    return r.stdout.strip() or "000"

dashboards = {
    "qsb_traders_live_serve_8847": http_code("http://127.0.0.1:8847/"),
    "qsb_studio_serve_8849": http_code("http://127.0.0.1:8849/"),
}

# Pot
pot = safe_json(ROOT / "data/registries/qsb_portfolio_pot.json")
pot_summary = {
    "open_positions": len(pot.get("open_positions", {})),
    "committed_gbp": round(pot.get("committed_gbp", 0.0), 2),
    "cap_gbp": pot.get("cap_gbp", 5000.0),
}

# Most recent pitstop
pitstops_dir = ROOT / "data/registries/pitstops"
last_pitstop = ""
if pitstops_dir.exists():
    ps_files = sorted(pitstops_dir.glob("pitstop_*.md"), key=lambda p: p.stat().st_mtime)
    if ps_files:
        last_pitstop = ps_files[-1].name

# Compose JSON state
state = {
    "ts": TS,
    "canonical_floor_count": floor_count,
    "team_roster": roster,
    "fleet": fleet,
    "dashboards": dashboards,
    "pot": pot_summary,
    "last_pitstop": last_pitstop,
    "unreal_project": "/vaults/nvme0/qsb_unreal_skyscraper/QSB_Skyscraper.uproject",
    "unreal_editor_running": int(subprocess.run(["bash", "-c", "pgrep -f 'UnrealEditor.*QSB_Skyscraper' | wc -l"],
                                                capture_output=True, text=True).stdout.strip() or 0),
}

(SHARED / "shared_project_state.json").write_text(json.dumps(state, indent=2))

# Compose markdown brief
brief = f"""# QSB Tower — shared project brief
_Generated: {TS}. Every team member reads this BEFORE doing work._

## What QSB is
The QSB Tower (Quantum Sovereign Brain Tower) is a 169-floor skyscraper-as-software running in `/vaults/nvme0/qsb_tower_v1`. Each numbered floor is a real department directory under `floors/`. The project includes:
- Live trader fleet on F41 (OANDA forex), F42 (Binance crypto testnet), F43 (Alpaca US equity paper)
- Browser dashboards on ports 8847 (traders live) + 8849 (studio)
- A separate Unreal Engine project at `/vaults/nvme0/qsb_unreal_skyscraper/` that visualises the tower
- A persistent AI team coordinated by Claude that builds + learns

## Canonical structure
- **Floor count: {floor_count}** — detected from `floors/*/floor_card.json`, NEVER hardcode this.

## Current live state
- Fleet: F41 OANDA {fleet['f41_oanda']} · F42 Binance {fleet['f42_binance']} · F43 Alpaca {fleet['f43_alpaca']} · Ensembles {fleet['ensembles']}
- Intel stack: bus={fleet['bus']} · belief_updater={fleet['belief_updater']} · regime={fleet['regime_detector']} · streams={fleet['streams']}
- Dashboards: 8847={dashboards['qsb_traders_live_serve_8847']} 8849={dashboards['qsb_studio_serve_8849']}
- Pot: {pot_summary['open_positions']} open, £{pot_summary['committed_gbp']} of £{pot_summary['cap_gbp']} committed
- Unreal editor: {'RUNNING' if state['unreal_editor_running'] else 'down'}
- Last pitstop: `{last_pitstop or 'none'}`

## Roles (hierarchy)
1. **Ross / Meh** — Owner, final boss.
2. **ChatGPT / Wren X directive** — Strategic boss instruction layer (multi-stage directives like this one).
3. **Claude CLI** — Execution captain / project build lead (me).
4. **Wren local 9B** (`qwen3.5:9b` via Ollama) — Second-in-command, local continuity brain, memory keeper, Claude's deputy.
5. **Hermes** (`hermes3:8b` or `hermes3-cpu:70b`) — Reasoning / architecture / symbolic review specialist.
6. **iQuest Coder** (`iquest-coder-cpu:40b`) — Coding / debugging / implementation specialist.
7. **OpenClaw** — Inspector / ticket creator / quality watcher (no model, JSONL ticket log).
8. **Smoke testers** — Proof + validation scripts.
9. **Maintenance crew** — System health, GPU/RAM/disk, build environment.

## Roster (real detection — see data/registries/qsb_team_model_roster_latest.json)
- Wren: `{roster.get('wren_local_model_id', 'unknown')}`
- Hermes: `{roster.get('hermes_local_model_id', 'unknown')}`
- iQuest Coder: `{roster.get('iquest_coder_local_model_id', 'unknown')}`
- LLaVA: `{roster.get('llava_vision_model_id', 'unknown')}`
- OpenAI + DeepSeek: advisory via `tools/qsb_consult_external.py`

## Tooling locations
- Trader fleet spawn: `scripts/spawn_all_traders_setsid.sh`, `scripts/spawn_ensembles.sh`
- UE5 MCP plugin: `/vaults/nvme0/qsb_unreal_skyscraper/Plugins/UnrealMCP/` (TCP 127.0.0.1:55557)
- F47 master: `data/registries/qsb_f47_team_records.jsonl`
- Pitstops: `data/registries/pitstops/`
- Wren local agent: `tools/qsb_wren_local_agent.py`
- Hermes local agent: `tools/qsb_hermes_local_agent.py`
- Provider consult: `tools/qsb_consult_external.py`
- Provider agentic (multi-turn + tools): `tools/qsb_provider_agent.py`

## Current top priorities (rolling)
1. Keep the trader fleet trading + dashboards green.
2. Push the full tower to private github (`devon3dp/skyscraperhq`).
3. Land Materials in the Unreal scene (the scene is still grey — `/tmp/qsb_ue_material_pass.py` recipe is ready).
4. Stand up persistent team orchestration (this directive).

## Current blockers
- MCP plugin can't create Materials/UMG/Blueprints — needs second patch OR UE Python.
- Hermes 70B cold-start times out at 240s; 8B returned empty this morning — needs diagnosis.
- iQuest Coder script has no `--task` flag; needs an adapter that calls the model directly.

## Rules (memorize)
- Don't hardcode floor counts — read `data/registries/qsb_canonical_tower_structure_latest.json`.
- Never push `vault/`, `.env*`, `CLAUDE.md`, secrets to public github.
- Real-money trading gates stay locked false.
- Every job stamps F47 (`data/registries/qsb_f47_team_records.jsonl`).
"""
(SHARED / "shared_project_brief.md").write_text(brief)
print(f"wrote {SHARED}/shared_project_brief.md ({len(brief)} chars)")
print(f"wrote {SHARED}/shared_project_state.json")
