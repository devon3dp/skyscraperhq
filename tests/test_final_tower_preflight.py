"""Final tower preflight — checks all infrastructure layers are staged correctly."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG  = ROOT / "data" / "registries"
sys.path.insert(0, str(ROOT / "src"))

def load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    return json.loads(p.read_text())

# ── Foundation ────────────────────────────────────────────────────────────────
floors = load("floors.json", [])
lifts  = load("lifts.json",  [])
assert len(floors) == 53,  f"Expected 53 floors, got {len(floors)}"
assert len(lifts)  >= 9,   f"Expected >=9 lifts, got {len(lifts)}"
assert len([f for f in floors if f.get("vacant")]) == 5, "Expected 5 vacant floors"

# ── Penthouse socket ──────────────────────────────────────────────────────────
sock = load("kernel_installation_socket.json", {})
assert sock.get("status") == "socket_ready_empty",  f"Socket status: {sock.get('status')}"
assert sock.get("kernel_installed") is False,       "kernel_installed must be False"

# ── Forbidden files absent ────────────────────────────────────────────────────
forbidden = [
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "penthouse" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
]
for f in forbidden:
    assert not f.exists(), f"Forbidden kernel file present: {f}"

# ── Candidate registries ──────────────────────────────────────────────────────
oc = load("openclaw_candidate_registry.json", [])
pa = load("pixel_agent_candidate_registry.json", [])
wc = load("worker_candidate_registry.json", [])
ac = load("adapter_candidate_registry.json", [])
assert len(oc) >= 1, "openclaw_candidate_registry.json empty"
assert len(pa) >= 1, "pixel_agent_candidate_registry.json empty"
assert len(wc) >= 1, "worker_candidate_registry.json empty"
assert len(ac) >= 1, "adapter_candidate_registry.json empty"

# All execution flags false
for e in oc + pa + wc + ac:
    cid = e.get("candidate_id", "?")
    assert not e.get("execution_enabled",        False), f"{cid} execution_enabled=True"
    assert not e.get("worker_execution_enabled",  False), f"{cid} worker_execution_enabled=True"
    assert not e.get("provider_execution_enabled",False), f"{cid} provider_execution_enabled=True"
    assert not e.get("model_inference_enabled",   False), f"{cid} model_inference_enabled=True"
    assert not e.get("live_dispatch_enabled",      False), f"{cid} live_dispatch_enabled=True"

# OpenClaw and pixel agents must be candidate_only
for e in oc + pa:
    assert e.get("current_status") == "candidate_only", \
        f"{e.get('candidate_id')} status={e.get('current_status')}, expected candidate_only"
    assert e.get("kernel_required_before_execution") is True, \
        f"{e.get('candidate_id')} missing kernel_required_before_execution"

# ── Kernel readiness module ───────────────────────────────────────────────────
from tower.kernel_readiness import KernelReadiness
r = KernelReadiness().run()
s = r["summary"]
assert s["critical_failures"] == 0,        f"Critical failures: {s['critical_failures']}"
assert s["kernel_installed"]  is False
assert s["readiness_status"] in (
    "READY_FOR_KERNEL_INTEGRATION", "READY_FOR_KERNEL_DESIGN_ONLY")

print("FINAL TOWER PREFLIGHT TEST PASSED")
print(f"  Floors: {len(floors)}  Lifts: {len(lifts)}  Vacant: {len([f for f in floors if f.get('vacant')])}")
print(f"  OpenClaw candidates: {len(oc)}  Pixel agents: {len(pa)}")
print(f"  Worker candidates: {len(wc)}  Adapter candidates: {len(ac)}")
print(f"  Kernel readiness: {s['readiness_status']}")
print(f"  Forbidden files: absent (correct)")
