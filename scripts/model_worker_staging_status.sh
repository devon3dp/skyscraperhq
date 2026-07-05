#!/usr/bin/env bash
# QSB Tower V1.3 — Model / Worker Staging Status
# Reports the staging state of all worker candidates and provider sockets.
# Does NOT activate, dispatch, or connect any worker or provider.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=============================================="
echo "  QSB Tower V1.3 — Model / Worker Staging"
echo "=============================================="
echo ""

python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, 'src')
from pathlib import Path

REG = Path('data/registries')

def load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else []
    return json.loads(p.read_text())

wc = load('worker_candidate_registry.json', [])
ac = load('adapter_candidate_registry.json', [])
ps = load('provider_sockets.json', [])

print("  Worker Candidates:")
for e in wc:
    print(f"    {e['candidate_id']:45s}  {e['current_status']}"
          f"  exec={e['execution_enabled']}")

print()
print("  Adapter Candidates:")
for e in ac:
    print(f"    {e['candidate_id']:45s}  {e['current_status']}"
          f"  exec={e['execution_enabled']}")

print()
print("  Provider Sockets:")
for e in (ps if isinstance(ps, list) else []):
    print(f"    {str(e.get('id','?')):45s}  exec={e.get('execution_enabled', '?')}")

print()
# Floor modules
try:
    from tower.agent_coordination import AgentCoordination
    d = AgentCoordination().dashboard()
    print(f"  Floor 25 Agent Coordination:")
    print(f"    status={d.get('status')}  candidates={d.get('candidate_workers')}"
          f"  worker_exec={d.get('worker_execution_enabled')}"
          f"  live_dispatch={d.get('live_dispatch_enabled')}")
except Exception as e:
    print(f"  Floor 25: error — {e}")

try:
    from tower.model_evaluation_department import ModelEvaluationDepartment
    d = ModelEvaluationDepartment().dashboard()
    print(f"  Floor 26 Model Evaluation:")
    print(f"    status={d.get('status')}  mode={d.get('evaluation_mode')}"
          f"  model_inference={d.get('model_inference_enabled')}")
except Exception as e:
    print(f"  Floor 26: error — {e}")

try:
    from tower.local_model_operations import LocalModelOperations
    d = LocalModelOperations().dashboard()
    print(f"  Floor 27 Local Models:")
    print(f"    detected={d.get('detected_models')}  inference={d.get('inference_enabled', False)}")
except Exception as e:
    print(f"  Floor 27: error — {e}")
PYEOF

echo ""
echo "=============================================="
