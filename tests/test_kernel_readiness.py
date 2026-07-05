"""Test kernel_readiness.py module — verifies READY_FOR_KERNEL_INTEGRATION status."""
import sys
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src" / "tower" / "kernel_readiness.py"), doraise=True)

from tower.kernel_readiness import KernelReadiness

r = KernelReadiness().run()
s = r["summary"]

assert s["critical_failures"] == 0,                      f"Critical failures: {s['critical_failures']}"
assert s["readiness_status"] in (
    "READY_FOR_KERNEL_INTEGRATION",
    "READY_FOR_KERNEL_DESIGN_ONLY"),                      f"Unexpected status: {s['readiness_status']}"
assert s["kernel_installed"]           is False,         "kernel_installed must be False"
assert s["kernel_logic_present"]       is False,         "kernel_logic_present must be False"
assert s["worker_execution_enabled"]   is False,         "worker_execution_enabled must be False"
assert s["provider_execution_enabled"] is False,         "provider_execution_enabled must be False"
assert s["model_inference_enabled"]    is False,         "model_inference_enabled must be False"
assert s["live_dispatch_enabled"]      is False,         "live_dispatch_enabled must be False"
assert s["checks_run"]                 >= 20,            f"Too few checks: {s['checks_run']}"
assert s["passed"]                     >= 20,            f"Too few passed: {s['passed']}"

# Confirm the report was written to disk
report_path = ROOT / "penthouse" / "kernel_occupancy_acceptance" / "latest_kernel_readiness_report.json"
assert report_path.exists(), "latest_kernel_readiness_report.json not written"

reg_path = ROOT / "data" / "registries" / "kernel_readiness_latest.json"
assert reg_path.exists(), "kernel_readiness_latest.json not written"

print("KERNEL READINESS TEST PASSED")
print(f"  Status         : {s['readiness_status']}")
print(f"  Checks         : {s['checks_run']}  Passed: {s['passed']}")
print(f"  Critical fails : {s['critical_failures']}")
print(f"  Warnings       : {s['warnings']}")
print(f"  kernel_installed: {s['kernel_installed']}")
