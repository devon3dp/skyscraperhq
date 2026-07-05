"""Dashboard must compile, serve 53 floors, show all required panels, no literal corruption."""
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
SERVER = ROOT / "src" / "dashboard" / "server.py"
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(SERVER), doraise=True)

spec = importlib.util.spec_from_file_location("srv", str(SERVER))
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# No literal backslash-n corruption
BN = chr(92) + "n"
assert BN not in mod.HTML, "Literal backslash-n corruption in HTML"

# Required panel strings
for s in [
    "towerRows", "/api/live", "QSB Tower V1.3",
    "Floor 25 Worker Recruitment", "Floor 26 Model Evaluation",
    "Floor 37 Simulation Labs",    "Floor 38 Sandbox Operations",
    "Lift Network",                "Vacant-Floor Activation Preview",
    "LIVE ACTIVITY FEED",          "penthouseBanner",
    "selectFloor",                 "selectLift",
]:
    assert s in mod.HTML, f"Missing from HTML: {s!r}"

# live_payload()
p = mod.live_payload()
c = p["status"]["counts"]
assert c["floors"]           == 53,    f"floors={c['floors']}"
assert c["lifts"]            >= 9,     f"lifts={c['lifts']}"
assert c["kernel_installed"] is False, "kernel_installed must be False"

ph = p["penthouse"]
assert ph.get("kernel_installed")     is False
assert ph.get("kernel_logic_present") is False

ag = p["agent_coordination"]
assert not ag.get("worker_execution_enabled", True)
assert not ag.get("live_dispatch_enabled",    True)

sb = p["sandbox_operations"]
assert sb.get("critical_failures", 1) == 0

me = p["model_evaluation"]
assert not me.get("model_inference_enabled", True)

print("DASHBOARD KERNEL READY TEST PASSED")
print(f"  Floors: {c['floors']}  Lifts: {c['lifts']}  Kernel: {c['kernel_installed']}")
