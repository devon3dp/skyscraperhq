"""OpenClaw and pixel-agent candidates must all be staged as candidate_only with execution disabled."""
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

oc = load("openclaw_candidate_registry.json")
pa = load("pixel_agent_candidate_registry.json")

assert len(oc) >= 1, "openclaw_candidate_registry.json is empty"
assert len(pa) >= 1, "pixel_agent_candidate_registry.json is empty"

EXEC_KEYS = [
    "execution_enabled", "worker_execution_enabled",
    "provider_execution_enabled", "model_inference_enabled", "live_dispatch_enabled",
]
REQUIRED_KEYS = [
    "candidate_id", "name", "type", "source", "target_floor", "current_status",
    "allowed_initial_mode", "blocked_initial_actions", "required_before_activation",
    "security_required", "source_audit_required", "sandbox_required",
    "model_evaluation_required", "kernel_required_before_execution",
    "execution_enabled", "worker_execution_enabled", "provider_execution_enabled",
    "model_inference_enabled", "live_dispatch_enabled",
]

for entry in oc:
    cid = entry.get("candidate_id", "?")
    for k in REQUIRED_KEYS:
        assert k in entry, f"{cid} missing required field: {k}"
    assert entry["current_status"] == "candidate_only", \
        f"{cid} status={entry['current_status']}, expected candidate_only"
    assert entry["kernel_required_before_execution"] is True, \
        f"{cid} kernel_required_before_execution must be True"
    for k in EXEC_KEYS:
        assert not entry[k], f"{cid} {k} must be False, got {entry[k]}"
    assert isinstance(entry["blocked_initial_actions"], list), \
        f"{cid} blocked_initial_actions must be a list"
    assert "execute" in entry["blocked_initial_actions"] or \
           "any_action" in entry["blocked_initial_actions"] or \
           "install" in entry["blocked_initial_actions"], \
        f"{cid} blocked_initial_actions must include execute/install/any_action"

for entry in pa:
    cid = entry.get("candidate_id", "?")
    assert entry.get("current_status") == "candidate_only", \
        f"{cid} status={entry.get('current_status')}"
    assert entry.get("kernel_required_before_execution") is True, \
        f"{cid} kernel_required_before_execution must be True"
    for k in EXEC_KEYS:
        assert not entry.get(k, False), f"{cid} {k} must be False"

# No OpenClaw or pixel-agent execution anywhere in adapter sockets
sockets = json.loads((REG / "adapter_sockets.json").read_text())
for s in sockets:
    if "openclaw" in str(s.get("id", "")).lower() or \
       "pixel" in str(s.get("id", "")).lower():
        assert not s.get("execution_enabled"), \
            f"Socket {s.get('id')} has execution_enabled=True"

print("OPENCLAW CANDIDATE STAGING TEST PASSED")
print(f"  OpenClaw candidates: {len(oc)}")
print(f"  Pixel-agent candidates: {len(pa)}")
print(f"  All status: candidate_only")
print(f"  All execution flags: False")
print(f"  All kernel_required_before_execution: True")
