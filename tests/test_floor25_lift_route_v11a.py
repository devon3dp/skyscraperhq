
import sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

from tower.agent_coordination import AgentCoordination

ac = AgentCoordination()
report = ac.run_prechecks()

assert report["floor"] == "floor_25"
assert report["kernel_installed"] is False
assert report["worker_execution_enabled"] is False
assert report["provider_execution_enabled"] is False
assert report["live_dispatch_enabled"] is False
assert report["critical_failures"] == 0, report

route_items = [x for x in report["items"] if x["check_id"] == "lift_routes_available"]
assert route_items, report

details = route_items[0]["details"]
assert details["floor24_to_local_models"]["id"] == "model_lift", details
assert details["floor25_to_security"]["id"] == "security_lift", details
assert details["floor25_to_router"]["id"] in ["service_lift", "main_mid_rise"], details

print("FLOOR 25 LIFT ROUTE V1.1A VALIDATION PASSED")
print("Status:", report["status"])
print("Critical failures:", report["critical_failures"])
print("Route:", details["route_architecture"])
print("Router lift:", details["floor25_to_router"]["id"])
print("Model lift:", details["floor24_to_local_models"]["id"])
print("Security lift:", details["floor25_to_security"]["id"])
