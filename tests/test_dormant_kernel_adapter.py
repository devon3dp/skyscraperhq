"""
Verify the DormantKernelAdapter:
- compiles cleanly
- dashboard() returns correct fields
- does NOT instantiate any kernel classes
- hash verification passes
- forbidden paths absent
- all safety flags False
"""
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

# Syntax check
py_compile.compile(str(ROOT / "src" / "tower" / "dormant_kernel_adapter.py"), doraise=True)

from tower.dormant_kernel_adapter import DormantKernelAdapter

adapter = DormantKernelAdapter()
d = adapter.dashboard()

# Core identity fields
assert d["kernel_name"]    == "QSB Kernel",                      f"name={d['kernel_name']}"
assert "4.6" in d["kernel_version"],                              f"version={d['kernel_version']}"
assert d["dormant_kernel_imported"] is True,                      "dormant_kernel_imported must be True"

# Safety: never instantiated kernel classes — verify via safety flags
assert d["kernel_installed"]           is False, "kernel_installed must be False"
assert d["kernel_logic_present"]       is True,  "kernel_logic_present must be True (files present)"
assert d["execution_enabled"]          is False, "execution_enabled must be False"
assert d["worker_execution_enabled"]   is False, "worker_execution_enabled must be False"
assert d["provider_execution_enabled"] is False, "provider_execution_enabled must be False"
assert d["model_inference_enabled"]    is False, "model_inference_enabled must be False"
assert d["live_dispatch_enabled"]      is False, "live_dispatch_enabled must be False"
assert d["activation_enabled"]         is False, "activation_enabled must be False"
assert d["direct_execution_allowed"]   is False, "direct_execution_allowed must be False"

# Files
assert d["imported_files_total"] >= 10, f"Expected >=10 imported files, got {d['imported_files_total']}"

# Hash verification
assert d["hash_verification"] == "all_match", f"Hash check failed: {d['hash_verification']}"

# Forbidden paths
assert d["forbidden_paths_absent"] is True, f"Forbidden paths found: {d['forbidden_paths_found']}"

# list_imported_files
files = adapter.list_imported_files()
assert "kernel_core.py" in files["kernel_files"],  "kernel_core.py missing from import"
assert "identity.json"  in files["kernel_files"],  "identity.json missing from import"
assert "penthouse.py"   in files["support_files"], "penthouse.py missing from support"

# check_forbidden_paths
fp = adapter.check_forbidden_paths()
assert fp["all_absent"] is True, f"Forbidden paths found: {fp['found']}"

# verify_hashes
hv = adapter.verify_hashes()
assert hv["status"] == "all_match", f"Hash drift: {hv}"

# compatibility_summary — must say not safe to instantiate
compat = adapter.compatibility_summary()
assert compat["safe_to_instantiate_kernel_classes"] is False, "Must not be safe to instantiate kernel classes"
assert compat["safe_for_dormant_import"] is True

print("DORMANT KERNEL ADAPTER TEST PASSED")
print(f"  Kernel name       : {d['kernel_name']}")
print(f"  Kernel version    : {d['kernel_version']}")
print(f"  Imported files    : {d['imported_files_total']}")
print(f"  Hash verification : {d['hash_verification']}")
print(f"  kernel_installed  : {d['kernel_installed']}")
print(f"  logic_present     : {d['kernel_logic_present']}")
print(f"  activation_enabled: {d['activation_enabled']}")
print(f"  Forbidden absent  : {d['forbidden_paths_absent']}")
