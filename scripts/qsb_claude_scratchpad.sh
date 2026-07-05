#!/usr/bin/env bash
# Drops you into a Python REPL with the Claude floor modules pre-loaded.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
exec python3 -i -c "
import sys
sys.path.insert(0, '${ROOT}')
from src.tower.model_floors.claude_floor import (
    LongLetterBox, UncertaintyJournal, RetractionWall, HonestyAudit,
    BeforeAnsweringProtocol, LetterDrawer, PushbackMeter,
)
from src.tower.model_floors.claude_floor.failure_mode_lab import FailureModeLab
from src.tower.model_floors.claude_floor.tower_garden import render as garden_render, haiku as garden_haiku
from src.tower.model_floors.claude_floor.daily_synthesis import synthesize as daily_synthesize
from src.tower.model_floors.claude_floor.pattern_library import (
    utc_ts, safe_write_json, append_jsonl, mirror_to_godot_project,
    SmokeCheck, run_smoke_checks, check_file_exists, check_no_pattern_in_tree,
)
from src.tower.model_floors.model_floor_router import ModelFloorRouter
print('Claude floor scratchpad — modules loaded.')
print('  Try: print(garden_render())   # ASCII tower')
print('  Try: print(garden_haiku())    # tiny haiku over current state')
print('  Try: print(daily_synthesize())  # end-of-session note')
print('  Try: BeforeAnsweringProtocol.clarifying_questions(\"Fix the thing.\")')
print()
"
