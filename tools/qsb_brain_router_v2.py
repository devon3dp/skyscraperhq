#!/usr/bin/env python3
"""
QSB Brain Router V2
Safe local router sidecar.

Endpoints:
  GET  /health.json
  GET  /nodes.json
  GET  /gate-check?gate=read_only
  GET  /route-test?prompt=hello&model=qwen2.5:14b
  POST /route-test {"prompt":"hello","model":"qwen2.5:14b"}
  POST /chat {"message":"...","task_gate":"read_only","model":"qwen2.5:14b"}

Truth policy:
  - Claude API is not used.
  - Every model response must include provider/model truth labels.
  - If no tool proof exists, say NO TOOL PROOF.
  - Write/execute gates are blocked unless explicitly approved by Ross.
"""

from __future__ import annotations

import json
import os
import sys
import time
import socket
import urllib.parse
import urllib.request
import urllib.error
import subprocess
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

SKY = Path("/vaults/nvme0/qsb_skyscraper")
TOWER = Path("/vaults/nvme0/qsb_tower_v1")
REG = TOWER / "data/registries"
LOGS = TOWER / "data/logs"
REG.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

VERSION = "brain_router_v2"
PORT = int(os.environ.get("QSB_BRAIN_ROUTER_V2_PORT", "8853"))

LOCAL_OLLAMA = os.environ.get("QSB_LOCAL_OLLAMA", "http://127.0.0.1:11434")
REMOTE_OLLAMA = os.environ.get("QSB_REMOTE_OLLAMA", "http://192.168.1.72:11434")
DEFAULT_MODEL = os.environ.get("QSB_ROUTER_MODEL", "qwen2.5:14b")
HEAVY_MODEL = os.environ.get("QSB_ROUTER_HEAVY_MODEL", "qwen2.5:32b")

TP_HEARTBEAT = "http://192.168.1.91:9110/heartbeat.json"
TP_PROOF = "http://192.168.1.91:9110/proof.json"

CALL_LOG = REG / "qsb_brain_router_v2_calls.jsonl"
STATUS_FILE = REG / "qsb_brain_router_v2_status.json"
PROOF_FILE = REG / "qsb_brain_router_v2_proof.json"
READINESS_FILE = REG / "qsb_team_readiness_latest.json"

ALLOWED_READ_GATES = {"read_only", "route_test", "health_check", "node_status"}
WRITE_APPROVAL_TOKEN = "ROSS_APPROVED_WRITE_WITH_BACKUP"
EXEC_APPROVAL_TOKEN = "ROSS_APPROVED_EXECUTE_WITH_PROOF"

def now() -> str:
    return datetime.now().isoformat()

def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

def read_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e), "_path": str(path)}
    return None

def http_get_json(url: str, timeout: float = 4.0) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QSB-BrainRouterV2"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": getattr(r, "status", None),
                "url": url,
                "json": json.loads(body),
                "tool_proof": "urllib_live_get",
                "timestamp": now(),
            }
    except Exception as e:
        return {
            "ok": False,
            "url": url,
            "error": str(e),
            "tool_proof": "urllib_live_get_failed",
            "timestamp": now(),
        }

def ollama_tags(base: str) -> dict:
    return http_get_json(base.rstrip("/") + "/api/tags", timeout=4.0)

def provider_available(base: str, model: str | None = None) -> tuple[bool, list[str], dict]:
    tags = ollama_tags(base)
    models: list[str] = []
    if tags.get("ok") and isinstance(tags.get("json"), dict):
        for m in tags["json"].get("models", []):
            name = m.get("name") or m.get("model")
            if name:
                models.append(name)
    if model:
        return any(x == model or x.startswith(model + ":") for x in models), models, tags
    return bool(models), models, tags

def choose_provider(model: str) -> dict:
    local_has, local_models, local_tags = provider_available(LOCAL_OLLAMA, model)
    if local_has:
        return {
            "provider_used": "local_ollama",
            "base_url": LOCAL_OLLAMA,
            "model_used": model,
            "fallback_used": False,
            "available_models_seen": local_models[:20],
            "tool_proof": "live_ollama_tags_local",
        }

    remote_has, remote_models, remote_tags = provider_available(REMOTE_OLLAMA, model)
    if remote_has:
        return {
            "provider_used": "remote_ollama",
            "base_url": REMOTE_OLLAMA,
            "model_used": model,
            "fallback_used": True,
            "available_models_seen": remote_models[:20],
            "tool_proof": "live_ollama_tags_remote",
        }

    return {
        "provider_used": "none",
        "base_url": None,
        "model_used": model,
        "fallback_used": False,
        "available_models_seen": {
            "local": local_models[:20],
            "remote": remote_models[:20] if "remote_models" in locals() else [],
        },
        "tool_proof": "model_not_found_in_live_ollama_tags",
    }

def ollama_generate(prompt: str, model: str = DEFAULT_MODEL, system: str | None = None, max_tokens: int = 256) -> dict:
    provider = choose_provider(model)
    if not provider.get("base_url"):
        return {
            "ok": False,
            "answer": "NO MODEL ROUTE PROOF: requested model not found in live Ollama tags.",
            "provider_used": provider["provider_used"],
            "model_used": model,
            "claude_api_used": False,
            "fallback_used": provider.get("fallback_used", False),
            "tool_proof": provider.get("tool_proof"),
            "timestamp": now(),
        }

    full_prompt = prompt
    if system:
        full_prompt = system.strip() + "\n\nUSER:\n" + prompt.strip()

    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": max_tokens,
        },
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            provider["base_url"].rstrip("/") + "/api/generate",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "QSB-BrainRouterV2"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            answer = parsed.get("response", "").strip()
            return {
                "ok": True,
                "answer": answer,
                "provider_used": provider["provider_used"],
                "model_used": model,
                "claude_api_used": False,
                "claude_avoided": True,
                "fallback_used": provider.get("fallback_used", False),
                "memory_source": "router_v2_live_prompt_plus_local_registry",
                "tool_proof": provider.get("tool_proof") + "+ollama_generate_http_200",
                "timestamp": now(),
                "raw_done": parsed.get("done"),
            }
    except Exception as e:
        return {
            "ok": False,
            "answer": "NO TOOL PROOF: Ollama generate failed.",
            "provider_used": provider["provider_used"],
            "model_used": model,
            "claude_api_used": False,
            "claude_avoided": True,
            "fallback_used": provider.get("fallback_used", False),
            "memory_source": "router_v2_live_prompt_plus_local_registry",
            "tool_proof": "ollama_generate_failed",
            "error": str(e),
            "timestamp": now(),
        }

def py_compile_status(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "compiles": False, "path": str(path)}
    try:
        subprocess.run([sys.executable, "-m", "py_compile", str(path)], check=True, capture_output=True, text=True, timeout=10)
        return {"exists": True, "compiles": True, "path": str(path)}
    except Exception as e:
        return {"exists": True, "compiles": False, "path": str(path), "error": str(e)}

def discover_asa() -> dict:
    roots = [SKY, TOWER]
    hits = []
    false_markers = ["/.venv/", "/site-packages/", "/.cache/", "/__pycache__/", "/external_oss/"]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if len(hits) >= 50:
                break
            s = str(p)
            if any(x in s for x in false_markers):
                continue
            name = p.name.lower()
            if name == "asa" or name.startswith("asa_") or name.endswith("_asa") or "asa_node" in name or "asa" == name.replace(".", ""):
                hits.append(s)
    return {
        "status": "FOUND_NEEDS_ENDPOINT" if hits else "NOT_PROVEN",
        "candidate_files": hits,
        "note": "Asa is not task-ready until a heartbeat/proof endpoint is found or created.",
    }

def nodes_status() -> dict:
    hq_persona = read_json(TOWER / "data/registries/hq_claude_local_persona.json")
    hq_status = read_json(TOWER / "data/registries/hq_claude_local_status.json")
    hq_proof = read_json(TOWER / "data/registries/hq_claude_local_proof.json")

    tp_hb = http_get_json(TP_HEARTBEAT)
    tp_pf = http_get_json(TP_PROOF)

    wren_files = [
        TOWER / "qsb_wren_dash.py",
        TOWER / "floors/floor_46_wren_bench/qsb_wren_dash.py",
        TOWER / "tools/qsb_wren_local_agent.py",
    ]
    wren_status = [py_compile_status(p) for p in wren_files]
    wren_ready = sum(1 for x in wren_status if x.get("compiles")) >= 2

    asa = discover_asa()

    return {
        "timestamp": now(),
        "proof_version": "qsb_nodes_status_v2",
        "hq_claude": {
            "ready": bool(hq_status and hq_proof and hq_status.get("node") == "HQ-Claude"),
            "persona": hq_persona,
            "status": hq_status,
            "proof": hq_proof,
            "claude_api_used": False,
        },
        "tp_pip": {
            "ready": bool(tp_hb.get("ok") and tp_pf.get("ok")),
            "heartbeat": tp_hb,
            "proof": tp_pf,
        },
        "wren_ren": {
            "ready": wren_ready,
            "ready_label": "YES_WITH_PROOF_LIMITS" if wren_ready else "NOT_READY",
            "compile_status": wren_status,
            "proof_limit": "Wren/Ren previously fabricated tool proof; keep NO TOOL PROOF rule active.",
        },
        "asa": asa,
        "ollama": {
            "local": ollama_tags(LOCAL_OLLAMA),
            "remote": ollama_tags(REMOTE_OLLAMA),
        },
        "safety": {
            "claude_api_used": False,
            "live_trading_enabled_by_router": False,
            "destructive_actions": False,
            "task_gates": ["read_only", "write_with_backup", "execute_with_approval", "emergency_stop"],
        },
    }

def health() -> dict:
    local_has_14, local_models, _ = provider_available(LOCAL_OLLAMA, DEFAULT_MODEL)
    remote_has_14, remote_models, _ = provider_available(REMOTE_OLLAMA, DEFAULT_MODEL)
    local_has_32, _, _ = provider_available(LOCAL_OLLAMA, HEAVY_MODEL)
    remote_has_32, _, _ = provider_available(REMOTE_OLLAMA, HEAVY_MODEL)

    node_status = nodes_status()

    data = {
        "status": "UP",
        "timestamp": now(),
        "router": "QSB Brain Router V2",
        "version": VERSION,
        "host": socket.gethostname(),
        "port": PORT,
        "roots": {
            "skyscraper": str(SKY),
            "tower": str(TOWER),
        },
        "provider_policy": {
            "default_model": DEFAULT_MODEL,
            "heavy_model": HEAVY_MODEL,
            "local_ollama": LOCAL_OLLAMA,
            "remote_ollama": REMOTE_OLLAMA,
            "claude_api_default": "blocked/avoided",
            "claude_api_used": False,
        },
        "model_availability": {
            "local_qwen14b": local_has_14,
            "remote_qwen14b": remote_has_14,
            "local_qwen32b": local_has_32,
            "remote_qwen32b": remote_has_32,
        },
        "team_readiness": {
            "hq_claude": "YES" if node_status["hq_claude"]["ready"] else "NO",
            "tp_pip": "YES" if node_status["tp_pip"]["ready"] else "NO",
            "wren_ren": node_status["wren_ren"]["ready_label"],
            "asa": node_status["asa"]["status"],
            "brain_router": "YES",
        },
        "truth_contract": {
            "must_include_provider_used": True,
            "must_include_model_used": True,
            "must_include_claude_api_used": True,
            "must_include_tool_proof": True,
            "no_tool_output_means": "NO TOOL PROOF",
        },
        "task_gates": {
            "read_only": "allowed",
            "route_test": "allowed",
            "write_with_backup": "requires token ROSS_APPROVED_WRITE_WITH_BACKUP",
            "execute_with_approval": "requires token ROSS_APPROVED_EXECUTE_WITH_PROOF",
            "emergency_stop": "reserved",
        },
    }
    write_json(STATUS_FILE, data)
    return data

def gate_check(gate: str, token: str | None = None) -> dict:
    if gate in ALLOWED_READ_GATES:
        return {
            "allowed": True,
            "gate": gate,
            "reason": "read-only gate allowed",
            "requires_backup": False,
            "timestamp": now(),
        }

    if gate == "write_with_backup":
        ok = token == WRITE_APPROVAL_TOKEN
        return {
            "allowed": ok,
            "gate": gate,
            "reason": "Ross approval token valid" if ok else "blocked: requires Ross approval token and backup",
            "requires_backup": True,
            "timestamp": now(),
        }

    if gate == "execute_with_approval":
        ok = token == EXEC_APPROVAL_TOKEN
        return {
            "allowed": ok,
            "gate": gate,
            "reason": "Ross execute approval token valid" if ok else "blocked: requires Ross execute approval token",
            "requires_backup": True,
            "timestamp": now(),
        }

    if gate == "emergency_stop":
        return {
            "allowed": False,
            "gate": gate,
            "reason": "emergency stop is not auto-triggered by router V2 endpoint",
            "timestamp": now(),
        }

    return {
        "allowed": False,
        "gate": gate,
        "reason": "unknown gate blocked",
        "timestamp": now(),
    }

def route_prompt(prompt: str, model: str, gate: str = "route_test", token: str | None = None) -> dict:
    gate_result = gate_check(gate, token)
    if not gate_result["allowed"]:
        return {
            "ok": False,
            "blocked": True,
            "gate": gate_result,
            "answer": "BLOCKED BY TASK GATE. No action taken.",
            "provider_used": "none",
            "model_used": model,
            "claude_api_used": False,
            "tool_proof": "gate_check",
            "timestamp": now(),
        }

    system = f"""
You are QSB Brain Router V2.
You must include truth labels in the answer.
Never claim Claude API was used.
If proof is not available, write NO TOOL PROOF.
Current route test gate: {gate}.
Return a concise useful answer.
"""
    result = ollama_generate(prompt, model=model, system=system, max_tokens=256)
    result["gate"] = gate_result
    append_jsonl(CALL_LOG, {
        "timestamp": now(),
        "kind": "route_prompt",
        "model": model,
        "gate": gate,
        "ok": result.get("ok"),
        "provider_used": result.get("provider_used"),
        "claude_api_used": result.get("claude_api_used"),
        "tool_proof": result.get("tool_proof"),
    })
    return result

class Handler(BaseHTTPRequestHandler):
    server_version = "QSBBrainRouterV2/1.0"

    def log_message(self, fmt, *args):
        append_jsonl(LOGS / "qsb_brain_router_v2_http.log", {
            "timestamp": now(),
            "client": self.client_address[0],
            "message": fmt % args,
        })

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"_raw": raw}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        if path in ["/", "/index.html"]:
            return self.send_json({
                "router": "QSB Brain Router V2",
                "status": "UP",
                "health": "/health.json",
                "nodes": "/nodes.json",
                "route_test": "/route-test?prompt=hello&model=qwen2.5:14b",
                "gate_check": "/gate-check?gate=read_only",
                "claude_api_used": False,
            })

        if path == "/health.json":
            return self.send_json(health())

        if path == "/proof.json":
            data = {
                "timestamp": now(),
                "proof_version": "brain_router_v2_proof_v1",
                "router_compile": "OK",
                "sidecar_port": PORT,
                "claude_api_used": False,
                "claude_avoided": True,
                "default_model": DEFAULT_MODEL,
                "heavy_model": HEAVY_MODEL,
                "truth_labels_enforced": True,
                "task_gates_enforced": True,
                "anti_fabrication_rule": "no tool output means NO TOOL PROOF",
            }
            write_json(PROOF_FILE, data)
            return self.send_json(data)

        if path == "/nodes.json":
            data = nodes_status()
            write_json(READINESS_FILE, data)
            return self.send_json(data)

        if path == "/gate-check":
            gate = qs.get("gate", ["read_only"])[0]
            token = qs.get("token", [None])[0]
            return self.send_json(gate_check(gate, token))

        if path == "/route-test":
            prompt = qs.get("prompt", ["Return QSB Brain Router V2 route test OK with truth labels."])[0]
            model = qs.get("model", [DEFAULT_MODEL])[0]
            gate = qs.get("gate", ["route_test"])[0]
            token = qs.get("token", [None])[0]
            return self.send_json(route_prompt(prompt, model, gate, token))

        return self.send_json({
            "status": "not_found",
            "path": path,
            "available": ["/health.json", "/proof.json", "/nodes.json", "/route-test", "/gate-check"],
        }, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_body_json()

        if path in ["/route-test", "/chat"]:
            prompt = body.get("prompt") or body.get("message") or "Return QSB Brain Router V2 route test OK with truth labels."
            model = body.get("model") or DEFAULT_MODEL
            gate = body.get("task_gate") or body.get("gate") or "read_only"
            token = body.get("approval_token")
            return self.send_json(route_prompt(prompt, model, gate, token))

        return self.send_json({"status": "not_found", "path": path}, status=404)

def main():
    data = health()
    write_json(PROOF_FILE, {
        "timestamp": now(),
        "proof_version": "brain_router_v2_proof_v1",
        "router_compile": "OK",
        "started": True,
        "sidecar_port": PORT,
        "claude_api_used": False,
        "claude_avoided": True,
        "default_model": DEFAULT_MODEL,
        "heavy_model": HEAVY_MODEL,
        "truth_labels_enforced": True,
        "task_gates_enforced": True,
    })
    print(f"QSB Brain Router V2 listening on 0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
