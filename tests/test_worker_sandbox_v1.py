import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

for rel in [
    "src/tower/floor41_paper_ledger.py",
    "src/tower/worker_sandbox.py",
]:
    py_compile.compile(str(ROOT / rel), doraise=True)

from tower.worker_sandbox import WorkerSandbox

s = WorkerSandbox().status()

assert s["sandbox"] == "worker_sandbox_v1"
assert s["sandbox_workers_enabled"] is True
assert s["worker_execution_enabled"] is False
assert s["openclaw_execution_enabled"] is False
assert s["autonomous_dispatch_enabled"] is False
assert s["worker_count"] >= 6
assert s["locks"]["live_trading_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["provider_execution_enabled"] is False
assert s["locks"]["external_provider_execution_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

print("WORKER SANDBOX V1 TEST PASSED")
print("  Worker count:", s["worker_count"])
print("  Worker execution:", s["worker_execution_enabled"])
print("  OpenClaw execution:", s["openclaw_execution_enabled"])
print("  Autonomous dispatch:", s["autonomous_dispatch_enabled"])
