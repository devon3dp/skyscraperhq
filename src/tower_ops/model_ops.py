"""Model Operations / Model Router V1.

Reports on local kernel model lane, Ollama lane, AirLLM advisory lane,
and the locked external-providers lane. Reads existing registries —
never enables external providers, never wires AirLLM into AutoLoop.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import urllib.request

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def _now(): return datetime.now(timezone.utc).isoformat()


def _load_json(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}


def status():
    policy = _load_json(ROOT / "data/registries/local_model_inference_policy.json")
    inf    = _load_json(ROOT / "data/registries/local_model_inference_status.json")
    air    = _load_json(ROOT / "data/registries/airllm_big_model_chamber.json")
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_OPERATIONS_V2",
        "selected_model": policy.get("selected_model") or inf.get("selected_model") or "llama3.2:latest",
        "local_model_inference_enabled": bool(inf.get("local_model_inference_enabled")),
        "ollama_detected":                bool(inf.get("ollama_detected")),
        "airllm_chamber_status":          air.get("status"),
        "airllm_advisory_only":           True,
        "external_providers_enabled":     False,
        "direct_provider_access":         False,
        "kernel_chat_routes": {"status": "/api/kernel_chat_status",
                                 "history": "/api/kernel_chat_history",
                                 "post": "/api/kernel_chat"},
    })


def _probe_ollama():
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            return {"reachable": True, "model_count": len((d.get("models") or [])),
                    "models": [(m.get("name") or "") for m in (d.get("models") or [])][:10]}
    except Exception as e:
        return {"reachable": False, "error": str(e)[:120]}


def lanes():
    s = status()
    ollama = _probe_ollama()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "lanes": [
            {
                "lane": "Local Kernel Model Lane",
                "status": "active" if s.get("local_model_inference_enabled") else "configured",
                "model": s.get("selected_model"),
                "health": "healthy",
                "allowed_usage":  ["kernel_chat", "advisory_reply"],
                "forbidden_usage":["live_trading", "openclaw_execution", "autonomous_dispatch"],
                "last_query_ts": None, "last_response_ts": None,
                "execution_allowed": False, "external_provider_access": False,
            },
            {
                "lane": "Ollama Lane",
                "status": "reachable" if ollama["reachable"] else "offline",
                "model": s.get("selected_model"),
                "model_count": ollama.get("model_count"),
                "models_available": ollama.get("models"),
                "health": "healthy" if ollama["reachable"] else "warning",
                "allowed_usage":  ["kernel_chat", "advisory_reply"],
                "forbidden_usage":["live_trading", "autonomous_dispatch"],
                "execution_allowed": False, "external_provider_access": False,
            },
            {
                "lane": "AirLLM Advisory Lane",
                "status": "installed_advisory_only" if s.get("airllm_chamber_status") else "not_installed",
                "model": "AirLLM Big Model Chamber",
                "health": "healthy",
                "allowed_usage":  ["manual_advisory_query_only"],
                "forbidden_usage":["autoloop_wiring", "trading_wiring", "openclaw_wiring"],
                "execution_allowed": False, "external_provider_access": False,
            },
            {
                "lane": "Research Model Lane",
                "status": "advisory_only",
                "model": "research_local_only",
                "health": "healthy",
                "allowed_usage":  ["research_summarization"],
                "forbidden_usage":["autonomous_web_access"],
                "execution_allowed": False,
            },
            {
                "lane": "Speech Model Lane",
                "status": "browser_only",
                "model": "browser_web_speech",
                "health": "healthy",
                "allowed_usage":  ["browser_tts", "browser_stt"],
                "forbidden_usage":["external_speech_provider"],
                "execution_allowed": False,
            },
            {
                "lane": "External Providers Locked Lane",
                "status": "LOCKED",
                "model": None,
                "health": "locked",
                "allowed_usage":  [],
                "forbidden_usage":["any_external_provider", "direct_provider_access"],
                "execution_allowed": False, "external_provider_access": False,
            },
        ],
    })


def local():    return stamp_safe({"ok": True, "ts": _now(), "lane": lanes()["lanes"][0]})
def airllm():   return stamp_safe({"ok": True, "ts": _now(), "lane": lanes()["lanes"][2]})
def router():
    s = status()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "router": {
            "Kernel ↔ Local Model":     "active" if s.get("local_model_inference_enabled") else "configured",
            "Kernel ↔ Speech":          "browser_web_speech",
            "Kernel ↔ Memory":          "registry+ledger",
            "Kernel ↔ AirLLM Advisory": "manual_only",
            "Kernel ↔ Research":        "advisory_only",
            "External Providers":       "LOCKED",
        },
    })


def manual_kernel_query(payload):
    """Proxy to existing kernel chat sidecar via the dashboard route. Local-only."""
    payload = payload or {}
    msg = (payload.get("message") or "").strip()
    if not msg: return {"ok": False, "error": "message_required"}
    try:
        data = json.dumps({"message": msg}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8766/api/kernel_chat",
                                       data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200],
                "fallback": "kernel chat sidecar unreachable"}


def manual_airllm_advisory(payload):
    """The AirLLM chamber is advisory only and not wired here.
    We DO NOT autonomously invoke the chamber. This endpoint returns a
    descriptor of how to manually use the lane.
    """
    return stamp_safe({
        "ok": True, "ts": _now(),
        "status": "advisory_lane_descriptor_only",
        "advisory_lane": {
            "chamber_path":  "/vaults/ai/airllm_lab",
            "manual_invocation_only": True,
            "execution_allowed":  False,
            "autoloop_wiring":    False,
            "trading_wiring":     False,
        },
        "message": "AirLLM advisory chamber is INSTALLED but remains advisory-only. " +
                    "Use the chamber's smoke test or manual CLI to invoke; never wired into AutoLoop.",
    })
