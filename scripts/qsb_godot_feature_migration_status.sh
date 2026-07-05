#!/usr/bin/env bash
# qsb_godot_feature_migration_status.sh — summary of old→Godot feature migration.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"

echo "============================================================"
echo "  QSB Godot · Feature Migration Status"
echo "  Phase: QSB_OLD_DASHBOARD_TO_GODOT_FEATURE_MIGRATION_V1"
echo "============================================================"

python3 - <<PY
import json
from pathlib import Path

ROOT = Path("${ROOT}")
REG = ROOT / "data/registries"

def load(name):
    p = REG / name
    if not p.exists(): return None
    try: return json.loads(p.read_text())
    except: return None

inv = load("qsb_old_dashboard_feature_inventory.json") or {}
matrix = load("qsb_old_to_godot_feature_parity_matrix.json") or {}
controls = load("qsb_godot_control_wiring_status.json") or {}
chat = load("qsb_godot_kernel_chat_migration_status.json") or {}
audio = load("qsb_godot_audio_voice_migration_status.json") or {}
nav = load("qsb_godot_floor_navigation_migration_status.json") or {}
trading = load("qsb_godot_trading_panel_migration_status.json") or {}
workers = load("qsb_godot_worker_openclaw_migration_status.json") or {}
depts = load("qsb_godot_department_panel_migration_status.json") or {}
ticker = load("qsb_godot_event_ticker_migration_status.json") or {}
tele = load("qsb_godot_telemetry_bridge_sources.json") or {}
layout = load("qsb_godot_layout_after_feature_migration_score.json") or {}

m_sum = matrix.get("summary", {})
print(f"  Old features inventoried:   {len(inv.get('features', []))}")
print(f"  Parity matrix entries:      {len(matrix.get('matrix', []))}")
print(f"    migrated:                 {m_sum.get('migrated', '—')}")
print(f"    visibly planned:          {m_sum.get('planned_visible', '—')}")
print(f"    silently missing:         {m_sum.get('silently_missing', '—')}")
print()
c_sum = controls.get("summary", {})
print(f"  Control bar controls:       {c_sum.get('total', '—')} (functional={c_sum.get('functional', '—')} planned={c_sum.get('planned', '—')})")
print()
print(f"  Kernel Chat present:        {chat.get('components', {}).get('input_box', False)}")
print(f"  Audio panel present:        {audio.get('controls', {}).get('voice', {}).get('present', False)}")
print(f"  Floor navigation:           {nav.get('features', {}).get('selected_floor', False)}")
print(f"  Trading panels present:     {trading.get('panels', {}).get('oanda_floor_41', {}).get('present', False)}")
print(f"  OpenClaw panel present:     {workers.get('features', {}).get('openclaw_current_floor', False)}")
print(f"  Department panels:          {depts.get('summary', {}).get('present', '—')} / {depts.get('summary', {}).get('total', '—')}")
print(f"  Event ticker present:       {ticker.get('shows_stale_data', False)}")
print(f"  Telemetry sources mapped:   {len(tele.get('direct_registry_fallbacks_used_by_panels', []))}")
print()
print(f"  Layout score:               {layout.get('score', '—')}/100 — {layout.get('verdict', '—')}")
print()
print("  Locks (always):")
print(f"    live_trading_enabled = OFF")
print(f"    live_payments_enabled = OFF")
print(f"    listings_publishing = OFF")
print(f"    openclaw_real_execution = OFF")
print(f"    autonomous_dispatch = OFF")
PY
