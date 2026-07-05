#!/usr/bin/env bash
# QSB Tower V1.3 — OpenClaw Candidate Status
# Reports the current staged status of all OpenClaw and pixel-agent candidates.
# Does NOT install, execute, or connect any framework.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=============================================="
echo "  QSB Tower V1.3 — OpenClaw Candidate Status"
echo "=============================================="
echo ""

python3 - <<'PYEOF'
import json
from pathlib import Path

REG = Path('data/registries')

def load(name):
    p = REG / name
    if not p.exists():
        return []
    return json.loads(p.read_text())

oc = load('openclaw_candidate_registry.json')
pa = load('pixel_agent_candidate_registry.json')

print("  OpenClaw Candidates:")
if not oc:
    print("    (none registered)")
for entry in oc:
    print(f"    {entry['candidate_id']:40s}  status={entry['current_status']}"
          f"  exec={entry['execution_enabled']}"
          f"  worker_exec={entry['worker_execution_enabled']}")

print()
print("  Pixel Agent Candidates:")
if not pa:
    print("    (none registered)")
for entry in pa:
    print(f"    {entry['candidate_id']:40s}  status={entry['current_status']}"
          f"  exec={entry['execution_enabled']}"
          f"  worker_exec={entry['worker_execution_enabled']}")

print()
# Safety check
all_safe = True
for e in oc + pa:
    if e.get('execution_enabled') or e.get('worker_execution_enabled'):
        print(f"  WARNING: {e['candidate_id']} has execution enabled!")
        all_safe = False

if all_safe:
    print("  All OpenClaw and pixel-agent candidates: CANDIDATE_ONLY, execution disabled.")
PYEOF

echo ""
echo "=============================================="
