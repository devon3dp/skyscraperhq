import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

adapter_file = ROOT / "src/tower/kernel_dialogue_adapter.py"
py_compile.compile(str(adapter_file), doraise=True)

from tower.kernel_dialogue_adapter import ask_kernel

r = ask_kernel("Test local-only kernel dialogue routing safety.", prefer_local_model=True)

assert r["ok"] is True
assert r["safety"]["kernel_installed"] is True
assert r["safety"]["QSBKernelCore_instantiated"] is True
assert r["safety"]["activation_status"] == "active_local_only"
assert r["safety"]["worker_execution_enabled"] is False
assert r["safety"]["provider_execution_enabled"] is False
assert r["safety"]["external_provider_execution_enabled"] is False
assert r["safety"]["openclaw_execution_enabled"] is False
assert r["safety"]["live_dispatch_enabled"] is False
assert r["safety"]["autonomous_workers_enabled"] is False

lm = r.get("local_model") or {}
if lm.get("used_local_model"):
    assert lm["safety"]["model_inference_scope"] == "local_only_kernel_dialogue"
    assert lm["safety"]["worker_execution_enabled"] is False
    assert lm["safety"]["provider_execution_enabled"] is False
    assert lm["safety"]["openclaw_execution_enabled"] is False
else:
    assert lm.get("safe_fallback") is True

print("KERNEL DIALOGUE LOCAL MODEL ROUTING TEST PASSED")
print("  Used local model:", lm.get("used_local_model"))
print("  Safe fallback:", lm.get("safe_fallback"))
