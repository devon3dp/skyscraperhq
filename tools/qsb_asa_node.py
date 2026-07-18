#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SKY = Path("/vaults/nvme0/qsb_skyscraper")
DATA = ROOT / "data/asa_node"
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/qsb_asa_node.log"
PORT = int(os.environ.get("QSB_ASA_PORT", "9122"))
BRAIN = os.environ.get("QSB_BRAIN_ROUTER_V2", "http://127.0.0.1:8853")

DATA.mkdir(parents=True, exist_ok=True)
REG.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(parents=True, exist_ok=True)

TASKS = DATA / "asa_tasks.jsonl"
RESULTS = DATA / "asa_results.jsonl"
STATUS = REG / "qsb_asa_status.json"
PROOF = REG / "qsb_asa_proof.json"
CARD = REG / "qsb_asa_node_card.json"

def now():
    return datetime.now().isoformat()

def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def append_jsonl(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

def brain_route(prompt: str, model: str = "qwen2.5:14b") -> dict:
    payload = {
        "message": prompt,
        "model": model,
        "task_gate": "read_only"
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            BRAIN.rstrip("/") + "/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {
            "ok": False,
            "answer": "NO TOOL PROOF: Asa could not reach Brain Router V2.",
            "error": str(e),
            "provider_used": "none",
            "model_used": model,
            "claude_api_used": False,
            "tool_proof": "brain_router_v2_call_failed",
            "timestamp": now(),
        }

def current_status() -> dict:
    data = {
        "timestamp": now(),
        "node": "Asa",
        "status": "alive",
        "mode": "local_task_node",
        "port": PORT,
        "role": "Task Council clerk, proof summariser, task receiver, registry writer",
        "brain_router_v2": BRAIN,
        "claude_api_used": False,
        "task_gate": "read_only by default",
        "destructive_actions": False,
        "files": {
            "tasks": str(TASKS),
            "results": str(RESULTS),
            "status": str(STATUS),
            "proof": str(PROOF),
            "card": str(CARD),
        }
    }
    write_json(STATUS, data)
    return data

def current_proof() -> dict:
    proof = {
        "timestamp": now(),
        "proof_version": "asa_node_v1",
        "node": "Asa",
        "status": "alive",
        "heartbeat_endpoint": f"http://127.0.0.1:{PORT}/heartbeat.json",
        "proof_endpoint": f"http://127.0.0.1:{PORT}/proof.json",
        "status_endpoint": f"http://127.0.0.1:{PORT}/status.json",
        "task_endpoint": f"http://127.0.0.1:{PORT}/task",
        "brain_router_v2": BRAIN,
        "claude_api_used": False,
        "writes_only_to": [str(TASKS), str(RESULTS), str(STATUS), str(PROOF), str(CARD)],
        "destructive_actions": False,
        "truth_policy": "If no tool output exists, say NO TOOL PROOF.",
    }
    write_json(PROOF, proof)
    return proof

def write_card():
    card = {
        "timestamp": now(),
        "node": "Asa",
        "title": "Asa",
        "role": "Task Council clerk and proof summariser",
        "status": "alive",
        "machine": "HQ",
        "port": PORT,
        "heartbeat_url": f"http://127.0.0.1:{PORT}/heartbeat.json",
        "proof_url": f"http://127.0.0.1:{PORT}/proof.json",
        "status_url": f"http://127.0.0.1:{PORT}/status.json",
        "task_url": f"http://127.0.0.1:{PORT}/task",
        "provider_route": "brain_router_v2",
        "model_default": "qwen2.5:14b",
        "claude_api_used": False,
        "proof_version": "asa_node_v1",
    }
    write_json(CARD, card)
    return card

def handle_task(task: dict) -> dict:
    task_id = task.get("task_id") or "asa_" + uuid.uuid4().hex[:10]
    instruction = task.get("instruction") or task.get("message") or "Summarise current task state."
    task_record = {
        "timestamp": now(),
        "task_id": task_id,
        "node": "Asa",
        "instruction": instruction,
        "task_gate": task.get("task_gate", "read_only"),
        "status": "accepted",
        "claude_api_used": False,
    }
    append_jsonl(TASKS, task_record)

    prompt = (
        "You are Asa, the QSB Task Council clerk. "
        "Complete this read-only task using concise proof language. "
        "Do not claim tool access you do not have. "
        "Instruction: " + instruction
    )
    routed = brain_route(prompt, task.get("model", "qwen2.5:14b"))

    result = {
        "timestamp": now(),
        "task_id": task_id,
        "node": "Asa",
        "status": "complete" if routed.get("ok") else "completed_with_router_warning",
        "instruction": instruction,
        "answer": routed.get("answer"),
        "provider_used": routed.get("provider_used"),
        "model_used": routed.get("model_used"),
        "claude_api_used": routed.get("claude_api_used", False),
        "tool_proof": routed.get("tool_proof"),
        "fallback_used": routed.get("fallback_used"),
    }
    append_jsonl(RESULTS, result)
    return result

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        append_jsonl(LOG, {"timestamp": now(), "client": self.client_address[0], "message": fmt % args})

    def send_json(self, data: dict, code: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        if n <= 0:
            return {}
        raw = self.rfile.read(n).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"message": raw}

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ["/", "/status.json"]:
            return self.send_json(current_status())
        if path == "/heartbeat.json":
            return self.send_json({
                "timestamp": now(),
                "node": "Asa",
                "status": "alive",
                "mode": "local_task_node",
                "port": PORT,
                "claude_api_used": False,
                "brain_router_v2": BRAIN,
            })
        if path == "/proof.json":
            return self.send_json(current_proof())
        if path == "/card.json":
            return self.send_json(write_card())
        if path == "/tasks.json":
            rows = []
            if TASKS.exists():
                rows = TASKS.read_text(encoding="utf-8").splitlines()[-50:]
            return self.send_json({"node": "Asa", "tasks_tail": rows})
        if path == "/results.json":
            rows = []
            if RESULTS.exists():
                rows = RESULTS.read_text(encoding="utf-8").splitlines()[-50:]
            return self.send_json({"node": "Asa", "results_tail": rows})
        return self.send_json({"error": "not_found", "path": path}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self.read_json_body()
        if path == "/task":
            return self.send_json(handle_task(body))
        return self.send_json({"error": "not_found", "path": path}, 404)

def main():
    current_status()
    current_proof()
    write_card()
    print(f"Asa node listening on 0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
