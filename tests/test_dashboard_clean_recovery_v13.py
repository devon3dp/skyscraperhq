import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
server = ROOT / "src/dashboard/server.py"

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location("dashboard_clean_recovery", str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()

assert payload["health"]["floors"] == 53, payload["health"]
assert payload["health"]["kernel_installed"] is False
assert "sandbox_operations" in payload
assert payload["sandbox_operations"]["floor"] == "floor_38"
assert payload["sandbox_operations"]["critical_failures"] == 0
assert payload["sandbox_operations"]["worker_execution_enabled"] is False
assert payload["sandbox_operations"]["provider_execution_enabled"] is False
assert "QSB Tower V1.3" in mod.HTML
assert "Floor 38 Sandbox Operations" in mod.HTML
assert "towerRows" in mod.HTML
assert "/api/live" in mod.HTML

print("DASHBOARD CLEAN RECOVERY V1.3 VALIDATION PASSED")
print("Floors:", payload["health"]["floors"])
print("Kernel installed:", payload["health"]["kernel_installed"])
print("Floor 38:", payload["sandbox_operations"]["status"])
print("Contained envelopes:", payload["sandbox_operations"]["contained_envelopes"])
