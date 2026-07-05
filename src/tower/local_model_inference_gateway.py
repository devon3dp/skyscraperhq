#!/usr/bin/env python3
"""
QSB Tower V1.3 — Local Model Inference Gateway

Local-only Ollama gateway for active QSB Kernel dialogue.

Safety boundaries:
- Only http://127.0.0.1:11434 is allowed.
- No external providers.
- No model pulls.
- No package installs.
- No workers.
- No OpenClaw execution.
- No autonomous dispatch.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import urllib.request
import urllib.error

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/local_model_inference.jsonl"

POLICY_PATH = REG / "local_model_inference_policy.json"
STATUS_PATH = REG / "local_model_inference_status.json"

ALLOWED_BASE_URL = "http://127.0.0.1:11434"


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


class LocalModelInferenceGateway:
    def __init__(self):
        self.policy = load_json(POLICY_PATH, {})
        self.base_url = self.policy.get("allowed_base_url") or ALLOWED_BASE_URL
        if self.base_url.rstrip("/") != ALLOWED_BASE_URL:
            raise RuntimeError(f"Blocked non-local model URL: {self.base_url}")

    def _request_json(self, path, payload=None, timeout=4):
        url = self.base_url.rstrip("/") + path
        if not url.startswith(ALLOWED_BASE_URL):
            raise RuntimeError(f"Blocked non-local URL: {url}")

        if payload is None:
            req = urllib.request.Request(url, method="GET")
        else:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def detect_ollama(self):
        try:
            data = self._request_json("/api/tags", timeout=2)
            models = []
            for item in data.get("models", []):
                name = item.get("name")
                if name:
                    models.append(name)

            selected = (
                os.environ.get("QSB_LOCAL_MODEL")
                or self.policy.get("selected_model")
                or (models[0] if models else None)
            )

            return {
                "ollama_detected": True,
                "base_url": self.base_url,
                "models": models,
                "selected_model": selected,
                "error": None,
            }
        except Exception as exc:
            return {
                "ollama_detected": False,
                "base_url": self.base_url,
                "models": [],
                "selected_model": None,
                "error": str(exc),
            }

    def status(self):
        detected = self.detect_ollama()
        effective_enabled = bool(
            self.policy.get("local_model_inference_enabled") is True
            and self.policy.get("ollama_local_inference_enabled") is True
            and detected.get("ollama_detected") is True
            and detected.get("selected_model")
        )

        status = {
            "status_ts": datetime.now(timezone.utc).isoformat(),
            "kernel_dialogue_model_routing": True,
            "local_model_inference_requested": True,
            "local_model_inference_enabled": effective_enabled,
            "ollama_local_inference_enabled": effective_enabled,
            "ollama_detected": detected.get("ollama_detected"),
            "selected_model": detected.get("selected_model"),
            "available_models": detected.get("models", []),
            "model_inference_scope": "local_only_kernel_dialogue",
            "local_only": True,
            "allowed_base_url": self.base_url,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "external_provider_execution_enabled": False,
            "openclaw_execution_enabled": False,
            "live_dispatch_enabled": False,
            "direct_provider_access": False,
            "autonomous_workers_enabled": False,
            "safe_fallback_if_unavailable": True,
            "error": detected.get("error"),
        }

        write_json(STATUS_PATH, status)
        return status

    def generate(self, prompt, system_context=None):
        status = self.status()

        if not status.get("local_model_inference_enabled"):
            result = {
                "ok": True,
                "used_local_model": False,
                "safe_fallback": True,
                "reply": "Local Ollama is not available or no local model is installed. Kernel dialogue remains symbolic/status-only.",
                "status": status,
            }
            append_log({"ts": datetime.now(timezone.utc).isoformat(), **result})
            return result

        model = status["selected_model"]

        full_prompt = prompt
        if system_context:
            full_prompt = (
                "You are the local-only speech layer for the active QSB Kernel. "
                "Do not claim worker/provider/OpenClaw execution is enabled. "
                "Report that workers, external providers, OpenClaw execution, and autonomous dispatch remain disabled.\n\n"
                f"Kernel context:\n{system_context}\n\nUser message:\n{prompt}"
            )

        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 320
            }
        }

        try:
            data = self._request_json("/api/generate", payload=payload, timeout=120)
            reply = data.get("response") or ""
            result = {
                "ok": True,
                "used_local_model": True,
                "local_only": True,
                "model": model,
                "reply": reply.strip(),
                "status": status,
                "safety": {
                    "worker_execution_enabled": False,
                    "provider_execution_enabled": False,
                    "external_provider_execution_enabled": False,
                    "openclaw_execution_enabled": False,
                    "live_dispatch_enabled": False,
                    "direct_provider_access": False,
                    "autonomous_workers_enabled": False,
                    "model_inference_scope": "local_only_kernel_dialogue",
                }
            }
        except Exception as exc:
            result = {
                "ok": True,
                "used_local_model": False,
                "safe_fallback": True,
                "reply": f"Local model call failed safely: {exc}. Kernel dialogue remains symbolic/status-only.",
                "status": status,
            }

        append_log({"ts": datetime.now(timezone.utc).isoformat(), **result})
        return result


def dashboard():
    return LocalModelInferenceGateway().status()


if __name__ == "__main__":
    gateway = LocalModelInferenceGateway()
    print(json.dumps(gateway.status(), indent=2))
