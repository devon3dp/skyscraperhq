import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/sandbox_performance_sidecar.py"), doraise=True)
py_compile.compile(str(ROOT / "src/dashboard/server.py"), doraise=True)

server = (ROOT / "src/dashboard/server.py").read_text(encoding="utf-8")
assert "qsb-performance-dashboard-panel" in server
assert "performanceDashboardPanel" in server
assert "api/performance/status" in server
assert "api/performance/run" in server

print("PERFORMANCE DASHBOARD PANEL V1 TEST PASSED")
