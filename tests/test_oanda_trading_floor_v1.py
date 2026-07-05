import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

for rel in [
    "src/tower/oanda_gateway.py",
    "src/tower/oanda_trading_floor.py",
]:
    py_compile.compile(str(ROOT / rel), doraise=True)

from tower.oanda_trading_floor import OANDATradingFloor

d = OANDATradingFloor().dashboard()

assert d["floor"] == "floor_41"
assert d["department"] == "OANDA Trading Floor"
assert d["environment"] == "practice"
assert d["paper_trading_enabled"] is True
assert d["live_trading_enabled"] is False
assert d["order_execution_enabled"] is False
assert d["practice_order_execution_enabled"] is False
assert d["worker_execution_enabled"] is False
assert d["provider_execution_enabled"] is False
assert d["openclaw_execution_enabled"] is False
assert d["autonomous_dispatch_enabled"] is False

print("OANDA TRADING FLOOR V1 TEST PASSED")
print("  Status:", d["status"])
print("  Account ready:", d["account_ready"])
print("  Pricing ready:", d["pricing_ready"])
print("  Live trading:", d["live_trading_enabled"])
print("  Order execution:", d["order_execution_enabled"])
