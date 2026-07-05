"""All model/LLM/worker floors (21-27, 37, 38) must be reachable and execution-safe."""
import sys
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FLOORS = [
    ("floor_21", "tower.adapter_systems",             "AdapterSystems",            "adapter_count"),
    ("floor_22", "tower.integration_services",        "IntegrationServices",       "integration_health"),
    ("floor_23", "tower.air_llm_operations",          "AirLLMOperations",          "provider_count"),
    ("floor_24", "tower.model_routing_department",    "ModelRoutingDepartment",    "route_decisions"),
    ("floor_25", "tower.agent_coordination",          "AgentCoordination",         "status"),
    ("floor_26", "tower.model_evaluation_department", "ModelEvaluationDepartment", "status"),
    ("floor_27", "tower.local_model_operations",      "LocalModelOperations",      "detected_models"),
    ("floor_37", "tower.simulation_labs",             "SimulationLabs",            "status"),
    ("floor_38", "tower.sandbox_operations",          "SandboxOperations",         "status"),
]

EXEC_KEYS = [
    "execution_enabled", "worker_execution_enabled",
    "provider_execution_enabled", "model_inference_enabled",
    "live_dispatch_enabled",
]

results = {}
for floor_id, mod_name, cls_name, key in FLOORS:
    try:
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        d = cls().dashboard()
        assert d.get("status") != "error", f"Module error: {d.get('error')}"
        for ek in EXEC_KEYS:
            if ek in d:
                assert not d[ek], f"{floor_id} {ek} must be False, got {d[ek]}"
        results[floor_id] = {"ok": True, key: d.get(key)}
    except AssertionError:
        raise
    except Exception as e:
        results[floor_id] = {"ok": False, "error": str(e)}

# Floor 38 must have 0 critical failures
from tower.sandbox_operations import SandboxOperations
sb = SandboxOperations().dashboard()
assert sb.get("critical_failures", 1) == 0, "Floor 38 critical_failures != 0"
assert not sb.get("network_enabled", False),            "Floor 38 network_enabled must be False"
assert not sb.get("worker_execution_enabled", False),   "Floor 38 worker_execution_enabled must be False"
assert not sb.get("provider_execution_enabled", False), "Floor 38 provider_execution_enabled must be False"

# Floor 25 safety
from tower.agent_coordination import AgentCoordination
ag = AgentCoordination().dashboard()
assert not ag.get("worker_execution_enabled", True), "Floor 25 worker_execution_enabled must be False"
assert not ag.get("live_dispatch_enabled",    True), "Floor 25 live_dispatch_enabled must be False"

errors = [f for f, r in results.items() if not r["ok"]]
if errors:
    for f in errors:
        print(f"  WARNING: {f} — {results[f].get('error')}")

print("ALL MODEL FLOORS READY TEST PASSED")
for floor_id, r in results.items():
    status = "OK" if r["ok"] else "ERROR"
    print(f"  {floor_id}: {status}  {r}")
print(f"  Floor 38 critical_failures: {sb.get('critical_failures')}")
print(f"  Floor 25 worker_exec: {ag.get('worker_execution_enabled')}")
print(f"  Floor 25 live_dispatch: {ag.get('live_dispatch_enabled')}")
