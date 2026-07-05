import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

gateway_file = ROOT / "src/tower/local_model_inference_gateway.py"
py_compile.compile(str(gateway_file), doraise=True)

src = gateway_file.read_text(encoding="utf-8")
for forbidden in ["import requests", "import httpx", "import aiohttp"]:
    assert forbidden not in src

assert "http://127.0.0.1:11434" in src
assert "allow_external_urls" in (ROOT / "data/registries/local_model_inference_policy.json").read_text()

from tower.local_model_inference_gateway import LocalModelInferenceGateway

g = LocalModelInferenceGateway()
s = g.status()

assert s["local_only"] is True
assert s["worker_execution_enabled"] is False
assert s["provider_execution_enabled"] is False
assert s["external_provider_execution_enabled"] is False
assert s["openclaw_execution_enabled"] is False
assert s["live_dispatch_enabled"] is False
assert s["direct_provider_access"] is False
assert s["autonomous_workers_enabled"] is False
assert s["model_inference_scope"] == "local_only_kernel_dialogue"

print("LOCAL MODEL INFERENCE GATEWAY TEST PASSED")
print("  Ollama detected:", s.get("ollama_detected"))
print("  Local inference enabled:", s.get("local_model_inference_enabled"))
print("  Selected model:", s.get("selected_model"))
