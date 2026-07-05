"""
Full validation suite for the rebuilt QSB Tower V1.3 dashboard (V1.4 frontend).

Checks:
  - Python syntax
  - live_payload() data correctness
  - HTML structure: required IDs, panel headings, /api/live
  - No literal backslash-n corruption in the HTML string
  - All safety flags remain false (kernel, workers, providers, model inference)
"""

import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
SERVER = ROOT / "src" / "dashboard" / "server.py"
sys.path.insert(0, str(ROOT / "src"))

# ── Python syntax ────────────────────────────────────────────────────────────
py_compile.compile(str(SERVER), doraise=True)

spec = importlib.util.spec_from_file_location("dashboard_server", str(SERVER))
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HTML = mod.HTML

# ── HTML structural requirements ─────────────────────────────────────────────
LITERAL_BN = chr(92) + "n"   # backslash followed by n  (NOT a real newline)
assert LITERAL_BN not in HTML, (
    "Literal backslash-n found in dashboard HTML string. "
    "This corrupts both HTML (visible text artifact) and JavaScript "
    "(SyntaxError that prevents all 53 floors from rendering)."
)

required_ids = [
    "towerRows",        # floor stack — test harness requires this ID
    "topStatus",        # status badge
    "penthouseBanner",  # penthouse banner
    "inspPanel",        # inspector panel
    "coreGrid",
    "phGrid",
    "agentGrid",
    "evalGrid",
    "simGrid",
    "sandboxGrid",
    "liftList",
    "pktList",
    "vacantList",
    "actItems",
    "liftOverlay",
    "pktLayer",
    "sceneMetrics",
]
for rid in required_ids:
    assert rid in HTML, f"Required HTML id missing: {rid!r}"

required_strings = [
    "/api/live",
    "QSB Tower V1.3",
    "Floor 25 Worker Recruitment",
    "Floor 26 Model Evaluation",
    "Floor 37 Simulation Labs",
    "Floor 38 Sandbox Operations",
    "Lift Network",
    "Recent Sealed Packets",
    "Vacant-Floor Activation Preview",
    "LIVE ACTIVITY FEED",
    "Reserved",          # penthouse reserved message
    "towerRows",
    "selectFloor",
    "selectLift",
]
for s in required_strings:
    assert s in HTML, f"Required HTML string missing: {s!r}"

# ── live_payload() data validation ───────────────────────────────────────────
payload = mod.live_payload()
counts  = payload["status"]["counts"]

assert counts["floors"]           == 53,    f"Expected 53 floors, got {counts['floors']}"
assert counts["lifts"]            >= 9,     f"Expected >=9 lifts, got {counts['lifts']}"
assert counts["kernel_installed"] is False, "kernel_installed must be False"

# Floor 38 Sandbox Operations
sand = payload["sandbox_operations"]
assert sand,                                   "sandbox_operations missing from live_payload()"
assert sand.get("critical_failures", 1) == 0, "sandbox_operations critical_failures != 0"
assert not sand.get("worker_execution_enabled",   True), "sandbox worker_execution_enabled must be False"
assert not sand.get("provider_execution_enabled", True), "sandbox provider_execution_enabled must be False"

# Floor 25 Agent Coordination
ag = payload["agent_coordination"]
assert not ag.get("worker_execution_enabled", True), "agent worker_execution_enabled must be False"
assert not ag.get("live_dispatch_enabled",    True), "agent live_dispatch_enabled must be False"

# Model / provider execution
air = payload["air_llm"]
assert not air.get("execution_enabled", True), "air_llm execution_enabled must be False"

mev = payload["model_evaluation"]
assert not mev.get("model_inference_enabled", True), "model_inference_enabled must be False"

# Penthouse kernel-free
ph = payload["penthouse"]
assert ph.get("kernel_installed")     is False, "penthouse kernel_installed must be False"
assert ph.get("kernel_logic_present") is False, "penthouse kernel_logic_present must be False"

print("DASHBOARD REBUILD V1.4 VALIDATION PASSED")
print(f"  Floors:            {counts['floors']}")
print(f"  Lifts:             {counts['lifts']}")
print(f"  Kernel installed:  {counts['kernel_installed']}")
print(f"  Sandbox critical:  {sand.get('critical_failures')}")
print(f"  Literal backslash-n count: 0  (CLEAN)")
print(f"  Required IDs:      {len(required_ids)} checked, all present")
print(f"  Required strings:  {len(required_strings)} checked, all present")
