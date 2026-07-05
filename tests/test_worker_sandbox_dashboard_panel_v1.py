import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/worker_sandbox_sidecar.py"), doraise=True)
py_compile.compile(str(ROOT / "src/dashboard/server.py"), doraise=True)

server = (ROOT / "src/dashboard/server.py").read_text(encoding="utf-8")
assert "qsb-worker-sandbox-panel" in server
assert "workerSandboxPanel" in server
assert "api/worker_sandbox/status" in server
assert "api/worker_sandbox/tick" in server

print("WORKER SANDBOX DASHBOARD PANEL V1 TEST PASSED")
