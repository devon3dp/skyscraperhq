import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/oanda_paper_strategy_lab.py"), doraise=True)

from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab

d = OANDAPaperStrategyLab().dashboard()

assert d["floor"] == "floor_41"
assert d["department"] == "OANDA Trading Floor"
assert d["paper_trading_enabled"] is True
assert d["paper_signal_generation_enabled"] is True
assert d["locks"]["live_trading_enabled"] is False
assert d["locks"]["order_execution_enabled"] is False
assert d["locks"]["practice_order_execution_enabled"] is False
assert d["locks"]["worker_execution_enabled"] is False
assert d["locks"]["provider_execution_enabled"] is False
assert d["locks"]["openclaw_execution_enabled"] is False
assert d["locks"]["autonomous_dispatch_enabled"] is False

print("OANDA PAPER STRATEGY LAB V1 TEST PASSED")
print("  Status:", d["status"])
print("  Latest:", d["latest_ts"])
