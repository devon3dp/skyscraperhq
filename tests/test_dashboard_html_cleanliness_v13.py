"""
Guard against literal backslash-n corruption being re-introduced into the
dashboard HTML/JS raw string in server.py.

Background: server.py uses r\"\"\"...\"\"\" (a Python raw string) for the
entire HTML+JS payload.  Inside a raw string, \n is NOT a newline — it
remains the two literal characters backslash and n.  If those appear:

  * In HTML context  → the browser renders visible "\n" text.
  * In JS context    → the parser hits a SyntaxError, the entire <script>
                       block fails to execute, and all 53 floors vanish from
                       the UI (topStatus badge stays frozen on "LOADING").

This test loads the server module and asserts the HTML string contains zero
occurrences of the two-character sequence backslash-n.  It also re-asserts
the core live_payload() invariants that were broken by those corruptions.
"""

import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "src" / "dashboard" / "server.py"

# ── Python syntax check ───────────────────────────────────────────────────────
py_compile.compile(str(SERVER), doraise=True)

spec = importlib.util.spec_from_file_location("dashboard_server", str(SERVER))
mod = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT / "src"))
spec.loader.exec_module(mod)

# ── HTML cleanliness: no literal backslash-n in the served payload ────────────
LITERAL_BACKSLASH_N = "\\" + "n"   # two chars: \ and n  (not a newline)
assert LITERAL_BACKSLASH_N not in mod.HTML, (
    "Literal '\\n' corruption found in dashboard HTML string. "
    "This causes a visible '\\n' text node in HTML context and/or a "
    "JavaScript SyntaxError that prevents the entire <script> from running, "
    "hiding all 53 floors and freezing the topStatus badge on LOADING."
)

# ── Required dashboard features still present ─────────────────────────────────
required_features = [
    "QSB Tower V1.3",
    "selectFloor",
    "selectLift",
    "p-trail",
    "zone-btn",
    "Vacant-Floor Activation Preview",
    "LIVE ACTIVITY FEED",
    "penthouseBanner",
    "towerRows",
    "sandboxGrid",
    "Floor 38 Sandbox Operations",
    "/api/live",
]
for feature in required_features:
    assert feature in mod.HTML, f"Missing dashboard feature: {feature!r}"

# ── live_payload() invariants ─────────────────────────────────────────────────
payload = mod.live_payload()
counts = payload["status"]["counts"]

assert counts["floors"] == 53,           f"Expected 53 floors, got {counts['floors']}"
assert counts["lifts"] >= 9,             f"Expected >=9 lifts, got {counts['lifts']}"
assert counts["kernel_installed"] is False, "kernel_installed must be False"

# Floor 38 Sandbox Operations
sb = payload["sandbox_operations"]
assert sb,                                    "sandbox_operations payload missing"
assert sb.get("critical_failures", 1) == 0,  "sandbox_operations has critical_failures"
assert not sb.get("worker_execution_enabled", True),   "sandbox worker_execution_enabled must be False"
assert not sb.get("provider_execution_enabled", True), "sandbox provider_execution_enabled must be False"

# Agent Coordination (Floor 25)
ag = payload["agent_coordination"]
assert not ag.get("worker_execution_enabled", True), "agent worker_execution_enabled must be False"
assert not ag.get("live_dispatch_enabled", True),    "agent live_dispatch_enabled must be False"

# Model / provider execution off
air = payload["air_llm"]
assert not air.get("execution_enabled", True), "air_llm execution_enabled must be False"

me = payload["model_evaluation"]
assert not me.get("model_inference_enabled", True), "model_inference_enabled must be False"

# Penthouse must remain kernel-free
ph = payload["penthouse"]
assert ph.get("kernel_installed") is False,      "penthouse kernel_installed must be False"
assert ph.get("kernel_logic_present") is False,  "penthouse kernel_logic_present must be False"

print("DASHBOARD HTML CLEANLINESS V1.3 VALIDATION PASSED")
print(f"  Floors:            {counts['floors']}")
print(f"  Lifts:             {counts['lifts']}")
print(f"  Kernel installed:  {counts['kernel_installed']}")
print(f"  Sandbox critical:  {sb.get('critical_failures')}")
print(f"  Literal \\n count:  0  (CLEAN)")
