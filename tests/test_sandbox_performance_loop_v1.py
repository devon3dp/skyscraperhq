import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/sandbox_performance_loop.py"), doraise=True)

from tower.sandbox_performance_loop import SandboxPerformanceLoop

s = SandboxPerformanceLoop().status()

assert s["phase"] == "SANDBOX_PERFORMANCE_LOOP_V1"
assert s["paper_only"] is True
assert s["not_financial_advice"] is True
assert s["locks"]["live_trading_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["worker_execution_enabled"] is False
assert s["locks"]["provider_execution_enabled"] is False
assert s["locks"]["external_provider_execution_enabled"] is False
assert s["locks"]["openclaw_execution_enabled"] is False
assert s["locks"]["autonomous_dispatch_enabled"] is False
assert s["locks"]["live_dispatch_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

print("SANDBOX PERFORMANCE LOOP V1 TEST PASSED")
print("  Status:", s["status"])
