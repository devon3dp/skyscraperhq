import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/sandbox_autoloop.py"), doraise=True)

from tower.sandbox_autoloop import SandboxAutoLoop

s = SandboxAutoLoop().status()

assert s["phase"] == "SANDBOX_AUTOLOOP_V1"
assert s["paper_only"] is True
assert s["not_financial_advice"] is True
assert s["locks"]["live_trading_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["worker_execution_enabled"] is False
assert s["locks"]["provider_execution_enabled"] is False
assert s["locks"]["external_provider_execution_enabled"] is False
assert s["locks"]["openclaw_execution_enabled"] is False
assert s["locks"]["openclaw_real_tool_execution_enabled"] is False
assert s["locks"]["autonomous_dispatch_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

print("SANDBOX AUTOLOOP V1 TEST PASSED")
print("  Status:", s["status"])
print("  Cycle:", s["cycle_index"])
