import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

for rel in [
    "src/tower/openclaw_sandbox_layer.py",
    "src/tower/openclaw_visual_sidecar.py",
    "src/dashboard/server.py"
]:
    py_compile.compile(str(ROOT / rel), doraise=True)

from tower.openclaw_sandbox_layer import OpenClawSandboxLayer

s = OpenClawSandboxLayer().status()

assert s["layer"] == "openclaw_sandbox_visual_layer_v1"
assert s["openclaw_sandbox_enabled"] is True
assert s["openclaw_visualization_enabled"] is True
assert s["openclaw_execution_enabled"] is False
assert s["locks"]["openclaw_execution_enabled"] is False
assert s["locks"]["worker_execution_enabled"] is False
assert s["locks"]["autonomous_dispatch_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

server = (ROOT / "src/dashboard/server.py").read_text(encoding="utf-8")
assert "qsb-openclaw-visual-panel" in server
assert "openclawVisualPanel" in server
assert "api/openclaw/status" in server
assert "api/openclaw/tick" in server

print("OPENCLAW SANDBOX VISUAL LAYER V1 TEST PASSED")
print("  OpenClaw sandbox enabled:", s["openclaw_sandbox_enabled"])
print("  OpenClaw execution:", s["openclaw_execution_enabled"])
print("  Worker count:", s["worker_count"])
