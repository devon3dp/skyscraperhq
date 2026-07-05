from pathlib import Path
import json
from datetime import datetime, UTC

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MODULE = ROOT / "src/tower/agent_coordination.py"

def now():
    return datetime.now(UTC).isoformat()

print("============================================================")
print(" QSB FLOOR 25 ROUTE PATCH V1.1A")
print(" Fixes indirect model route through Floor 24")
print(" No workers activated. No providers enabled. No kernel.")
print("============================================================")

if not MODULE.exists():
    raise SystemExit(f"Missing module: {MODULE}")

src = MODULE.read_text(encoding="utf-8")
backup = MODULE.with_suffix(".py.backup_before_floor25_route_v11a")
backup.write_text(src, encoding="utf-8")
print(f"Backup written: {backup}")

old = 'model = net.choose("floor_25", "floor_27", "model_lift")'
new = 'model = net.choose("floor_24", "floor_27", "model_lift")'

if old not in src:
    print("Direct model route line not found; checking if already patched.")
else:
    src = src.replace(old, new)

old_details = 'lift_details = {"service": service, "security": security, "model": model}'
new_details = '''lift_details = {
                "route_architecture": "floor_25 -> floor_24 -> floor_27",
                "floor25_to_router": service,
                "floor24_to_local_models": model,
                "floor25_to_security": security,
                "note": "Floor 25 does not need direct model_lift access. It reaches model systems through Floor 24 routing."
            }'''

if old_details in src:
    src = src.replace(old_details, new_details)

MODULE.write_text(src, encoding="utf-8")

# ------------------------------------------------------------
# Clean manifest: Floor 25 should not claim direct model_lift access
# ------------------------------------------------------------
manifest_path = ROOT / "floors/floor_25_agent_coordination_department/floor_manifest.json"
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    lift_access = manifest.get("lift_access", [])
    manifest["lift_access"] = [
        x for x in lift_access
        if x != "model_lift"
    ]

    if "main_mid_rise" not in manifest["lift_access"]:
        manifest["lift_access"].insert(0, "main_mid_rise")
    if "service_lift" not in manifest["lift_access"]:
        manifest["lift_access"].append("service_lift")
    if "security_lift" not in manifest["lift_access"]:
        manifest["lift_access"].append("security_lift")
    if "emergency_stairwell" not in manifest["lift_access"]:
        manifest["lift_access"].append("emergency_stairwell")

    manifest["indirect_model_lift_access"] = {
        "enabled": True,
        "transfer_floor": "floor_24",
        "path": ["floor_25", "floor_24", "floor_27"],
        "first_leg": {
            "from": "floor_25",
            "to": "floor_24",
            "allowed_lifts": ["service_lift", "main_mid_rise"]
        },
        "second_leg": {
            "from": "floor_24",
            "to": "floor_27",
            "allowed_lifts": ["model_lift"]
        },
        "sealed_packets": True,
        "direct_provider_access": False
    }

    manifest["patched_v11a"] = now()
    manifest["notice"] = "Floor 25 is recruitment only. It reaches model operations indirectly through Floor 24; no worker execution is enabled."

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Updated Floor 25 manifest with indirect model route.")

# ------------------------------------------------------------
# Patch config wording if present
# ------------------------------------------------------------
cfg = ROOT / "config/agent_coordination.yaml"
if cfg.exists():
    text = cfg.read_text(encoding="utf-8")
    text = text.replace("    - model_lift\n", "")
    if "model_lift_indirect_via: floor_24" not in text:
        text += """

indirect_model_access:
  model_lift_indirect_via: floor_24
  first_leg:
    from: floor_25
    to: floor_24
    allowed_lifts:
      - service_lift
      - main_mid_rise
  second_leg:
    from: floor_24
    to: floor_27
    allowed_lifts:
      - model_lift
  direct_provider_access: false
  execution_enabled: false
"""
    cfg.write_text(text, encoding="utf-8")
    print("Updated agent coordination config.")

# ------------------------------------------------------------
# Create validation test
# ------------------------------------------------------------
test = ROOT / "tests/test_floor25_lift_route_v11a.py"
test.write_text('''
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
''', encoding="utf-8")

print()
print("Patch installed.")
print("Next run:")
print("export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src")
print("python3 tests/test_floor25_lift_route_v11a.py")
print("python3 tests/test_agent_coordination_v11.py")
print("python3 tests/test_dashboard_floor25_v11.py")
