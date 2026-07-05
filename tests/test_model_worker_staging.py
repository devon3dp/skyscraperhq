"""Worker and adapter candidates must all be staged with execution disabled."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG  = ROOT / "data" / "registries"
sys.path.insert(0, str(ROOT / "src"))

def load(name):
    p = REG / name
    assert p.exists(), f"Registry missing: {name}"
    return json.loads(p.read_text())

wc = load("worker_candidate_registry.json")
ac = load("adapter_candidate_registry.json")

assert len(wc) >= 1, "worker_candidate_registry.json is empty"
assert len(ac) >= 1, "adapter_candidate_registry.json is empty"

EXEC_KEYS = [
    "execution_enabled", "worker_execution_enabled",
    "provider_execution_enabled", "model_inference_enabled", "live_dispatch_enabled",
]
REQUIRED_W = [
    "candidate_id", "name", "type", "source", "target_floor", "current_status",
    "allowed_initial_mode", "blocked_initial_actions", "required_before_activation",
    "kernel_required_before_execution",
    "execution_enabled", "worker_execution_enabled", "provider_execution_enabled",
    "model_inference_enabled", "live_dispatch_enabled",
]

for entry in wc:
    cid = entry.get("candidate_id", "?")
    for k in REQUIRED_W:
        assert k in entry, f"{cid} missing field: {k}"
    for k in EXEC_KEYS:
        assert not entry[k], f"{cid} {k} must be False, got {entry[k]}"
    assert entry["current_status"] in ("candidate_only", "socket_ready_not_connected",
                                       "socket_ready_optional", "inventory_only"), \
        f"{cid} unexpected status: {entry['current_status']}"

for entry in ac:
    cid = entry.get("candidate_id", "?")
    for k in EXEC_KEYS:
        if k in entry:
            assert not entry[k], f"Adapter {cid} {k} must be False"
    assert not entry.get("hardwired", False), f"Adapter {cid} must not be hardwired"

# Floor 25 live checks
from tower.agent_coordination import AgentCoordination
d = AgentCoordination().dashboard()
assert d.get("status") != "error",                      "AgentCoordination returned error"
assert not d.get("worker_execution_enabled", True),     "worker_execution_enabled must be False"
assert not d.get("live_dispatch_enabled",    True),     "live_dispatch_enabled must be False"

# Floor 26 live checks
from tower.model_evaluation_department import ModelEvaluationDepartment
d2 = ModelEvaluationDepartment().dashboard()
assert d2.get("status") != "error",                     "ModelEvaluationDepartment returned error"
assert not d2.get("model_inference_enabled", True),     "model_inference_enabled must be False"

print("MODEL / WORKER STAGING TEST PASSED")
print(f"  Worker candidates   : {len(wc)}")
print(f"  Adapter candidates  : {len(ac)}")
print(f"  All execution flags : False")
print(f"  No hardwired adapters")
print(f"  Floor 25 worker_exec: {d.get('worker_execution_enabled')}")
print(f"  Floor 25 dispatch   : {d.get('live_dispatch_enabled')}")
print(f"  Floor 26 inference  : {d2.get('model_inference_enabled')}")
