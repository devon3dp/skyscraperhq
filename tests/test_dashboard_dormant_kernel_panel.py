"""
Verify the dashboard includes the Dormant Kernel Import panel and all required safety fields.
"""
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT   = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src" / "dashboard" / "server.py"
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(SERVER), doraise=True)

spec = importlib.util.spec_from_file_location("srv", str(SERVER))
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HTML = mod.HTML

# No literal backslash-n corruption
BN = chr(92) + "n"
assert BN not in HTML, "Literal backslash-n corruption in dashboard HTML"

# Required new panel strings
assert "Dormant Kernel Import"         in HTML, "Missing: Dormant Kernel Import panel heading"
assert "Kernel Integration Readiness"  in HTML, "Missing: Kernel Integration Readiness panel heading"
assert "dormantKernelGrid"             in HTML, "Missing: dormantKernelGrid element"
assert "kernelReadinessGrid"           in HTML, "Missing: kernelReadinessGrid element"
assert "dormantKernelBadge"            in HTML, "Missing: dormantKernelBadge element"
assert "kernelReadinessBadge"          in HTML, "Missing: kernelReadinessBadge element"

# Pre-existing required strings still present
for s in [
    "towerRows", "/api/live", "QSB Tower V1.3",
    "Floor 25 Worker Recruitment", "Floor 26 Model Evaluation",
    "Floor 37 Simulation Labs",    "Floor 38 Sandbox Operations",
    "Lift Network",                "LIVE ACTIVITY FEED",
]:
    assert s in HTML, f"Missing from HTML: {s!r}"

# live_payload() dormant kernel fields
payload = mod.live_payload()
c  = payload["status"]["counts"]
dk = payload["dormant_kernel"]
kr = payload["kernel_readiness"]

assert c["floors"]           == 53,   f"floors={c['floors']}"
assert c["kernel_installed"] is False, "kernel_installed must be False"

# Dormant kernel adapter fields
assert dk.get("dormant_kernel_imported") is True,  "dormant_kernel_imported must be True"
assert dk.get("kernel_installed")        is False, "kernel_installed must be False"
assert dk.get("kernel_logic_present")    is True,  "kernel_logic_present must be True"
assert dk.get("activation_enabled")      is False, "activation_enabled must be False"
assert dk.get("execution_enabled")       is False, "execution_enabled must be False"
assert dk.get("worker_execution_enabled") is False, "worker_execution_enabled must be False"
assert dk.get("provider_execution_enabled") is False
assert dk.get("model_inference_enabled")    is False
assert dk.get("live_dispatch_enabled")      is False

# Kernel readiness fields
assert kr.get("kernel_installed")        is False
assert kr.get("kernel_logic_present")    is True
assert kr.get("dormant_kernel_imported") is True
assert kr.get("dormant_kernel_activation_enabled") is False
assert kr.get("critical_failures", 1)   == 0
assert kr.get("readiness_status")       in (
    "READY_FOR_DORMANT_KERNEL_REVIEW",
    "READY_FOR_KERNEL_INTEGRATION",
    "READY_FOR_KERNEL_DESIGN_ONLY",
)

# Forbidden direct kernel paths still absent
forbidden = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]
for f in forbidden:
    assert not f.exists(), f"FORBIDDEN kernel path found: {f}"

print("DASHBOARD DORMANT KERNEL PANEL TEST PASSED")
print(f"  Floors                : {c['floors']}")
print(f"  Dormant Kernel Panels : present in HTML")
print(f"  dormant_kernel_imported : {dk.get('dormant_kernel_imported')}")
print(f"  kernel_installed        : {dk.get('kernel_installed')}")
print(f"  kernel_logic_present    : {dk.get('kernel_logic_present')}")
print(f"  activation_enabled      : {dk.get('activation_enabled')}")
print(f"  Readiness status        : {kr.get('readiness_status')}")
print(f"  Forbidden paths         : all absent")
print(f"  No literal backslash-n  : CLEAN")
