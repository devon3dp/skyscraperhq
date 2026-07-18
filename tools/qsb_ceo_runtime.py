#!/usr/bin/env python3
"""qsb_ceo_runtime.py — real non-Claude local runtime for Acer + ThinkPad.

Ross 2026-07-07 order: restore Acer/ThinkPad as REAL local runtimes like Wren,
but with their OWN identity/memory and a NON-CLAUDE Brain Router backend.
Claude HQ coordinates only; this runtime never calls Claude for worker tasks.

Backend = Brain Router (caller=<ceo>) → Acer:DeepSeek first, TP:OpenAI first,
Claude structurally blocked for these callers (see qsb_brain_router._caller_order).

Components: identity loader · memory reader (read-only) · append-only learning
writer (shrink-guarded) · Brain Router client · dashboard/API · safety guard.

USAGE
    python3 tools/qsb_ceo_runtime.py --ceo acer   --serve --port 8862
    python3 tools/qsb_ceo_runtime.py --ceo tp_pip --serve --port 8861
    python3 tools/qsb_ceo_runtime.py --ceo acer   --whoami            # one-shot
    python3 tools/qsb_ceo_runtime.py --ceo acer   --smoke             # self-test
"""
from __future__ import annotations
import argparse, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
sys.path.insert(0, str(ROOT / "tools"))

def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# ── per-CEO config (identity/memory stay LOCAL and distinct; no Wren identity) ──
CEOS = {
    "acer": {
        "id": "acer_cass", "name": "Acer-Cass", "role": "Data Foundry / model-serving CEO",
        "card": REG / "qsb_acer_cass_operator_card.json",
        "lessons": REG / "lessons_acer_cass.jsonl",         # OLD MEMORY (read-only)
        "notes": REG / "acer_cass_notes.jsonl",             # NEW NOTES (append-only)
        "default_provider": "deepseek", "port": 8862,
        "local_fallback_model": "llama3.2:latest",
    },
    "tp_pip": {
        "id": "tp_pip", "name": "TP-Pip", "role": "ThinkPad Command Cathedral CEO",
        "card": REG / "qsb_tp_pip_operator_card.json",
        "lessons": REG / "lessons_tp_pip.jsonl",
        "notes": REG / "tp_pip_notes.jsonl",
        "default_provider": "openai", "port": 8861,
        "local_fallback_model": None,
    },
}

def cfg(ceo: str) -> dict:
    key = ceo.lower().replace("-", "_")
    if key in ("acer", "acer_cass", "cass", "asa"): return CEOS["acer"]
    if key in ("tp", "tp_pip", "thinkpad", "pip"):  return CEOS["tp_pip"]
    raise SystemExit(f"unknown ceo: {ceo}")

# ── identity loader ──
def load_identity(c: dict) -> dict:
    card = {}
    try:
        if c["card"].exists(): card = json.loads(c["card"].read_text())
    except Exception:
        card = {}
    return {"id": c["id"], "name": c["name"], "role": c["role"],
            "identity_file": str(c["card"].relative_to(ROOT)),
            "card_keys": list(card)[:20], "backend": "brain_router_non_claude",
            "default_provider": c["default_provider"], "claude_allowed": False}

# ── memory reader (READ-ONLY) ──
def read_memory(c: dict, n: int = 3) -> dict:
    rows, count = [], 0
    if c["lessons"].exists():
        lines = c["lessons"].read_text().splitlines()
        count = len(lines)
        for ln in lines[-n:]:
            try: rows.append(json.loads(ln))
            except Exception: rows.append({"raw": ln[:200]})
    return {"lessons_file": str(c["lessons"].relative_to(ROOT)),
            "total_lessons": count, "latest": rows}

# ── learning writer (APPEND-ONLY + shrink guard; never touches old memory) ──
def write_note(c: dict, text: str, kind: str = "note") -> dict:
    p = c["notes"]
    p.parent.mkdir(parents=True, exist_ok=True)
    before_bytes = p.stat().st_size if p.exists() else 0
    before_lines = sum(1 for _ in p.open()) if p.exists() else 0
    row = json.dumps({"ts": _utc(), "who": c["id"], "kind": kind, "text": text})
    with open(p, "a") as f:            # append only — never truncates
        f.write(row + "\n"); f.flush(); os.fsync(f.fileno())
    after_bytes = p.stat().st_size
    after_lines = sum(1 for _ in p.open())
    if after_bytes < before_bytes or after_lines < before_lines:
        return {"ok": False, "err": "MEMORY SAFETY FAILURE",
                "before_lines": before_lines, "after_lines": after_lines}
    return {"ok": True, "notes_file": str(p.relative_to(ROOT)),
            "before_lines": before_lines, "after_lines": after_lines}

# ── Brain Router client (NON-CLAUDE backend) ──
def brain_router_call(c: dict, prompt: str, task: str = "chat") -> dict:
    import qsb_brain_router as br
    reply, meta = br.route(prompt, task=task, tier="worker", caller=c["id"])
    return {"provider_used": meta.get("provider"), "model_used": meta.get("model"),
            "claude_avoided": bool(meta.get("claude_avoided", meta.get("provider") not in ("claude",))),
            "claude_blocked": bool(meta.get("claude_blocked", False)),
            "tried": meta.get("tried"), "latency_s": round(meta.get("latency_s", 0), 2),
            "cost_usd": meta.get("cost_usd", 0), "reply_head": (reply or "")[:200]}

# ── dashboard/API ──
def make_handler(c: dict):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/health", "/"):
                self._send({"ok": True, "ceo": c["id"], "name": c["name"],
                            "backend": "brain_router_non_claude", "ts": _utc()})
            elif path == "/whoami":
                self._send(load_identity(c))
            elif path == "/memory":
                self._send(read_memory(c, 5))
            elif path == "/status":
                self._send({"ceo": c["id"], "name": c["name"], "role": c["role"],
                            "default_provider": c["default_provider"], "claude_allowed": False,
                            "backend": "brain_router_non_claude", "pid": os.getpid(), "ts": _utc()})
            elif path == "/learning/latest":
                rows = []
                if c["notes"].exists():
                    for ln in c["notes"].read_text().splitlines()[-3:]:
                        try: rows.append(json.loads(ln))
                        except Exception: pass
                self._send({"latest_notes": rows})
            elif path in ("/dash", "/dashboard"):
                # HTML status dashboard for the boardroom quad-monitor panels.
                ident = load_identity(c); mem = read_memory(c, 3)
                theme = "#f59e0b" if c["id"] == "acer_cass" else "#22d3ee"
                notes = ""
                if c["notes"].exists():
                    for ln in c["notes"].read_text().splitlines()[-4:]:
                        try:
                            o = json.loads(ln); notes = f"<div class='n'>· {o.get('kind','')}: {str(o.get('text',''))[:120]}</div>" + notes
                        except Exception: pass
                html = f"""<!doctype html><html><head><meta charset=utf-8>
<meta http-equiv=refresh content=30>
<meta name=viewport content='width=device-width,initial-scale=1'>
<style>body{{margin:0;font-family:system-ui,sans-serif;background:#0b1020;color:#e8eefc}}
.wrap{{padding:16px}} h1{{margin:0;font-size:22px;color:{theme}}}
.role{{color:#94a3b8;font-size:13px;margin:2px 0 12px}}
.row{{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}}
.pill{{background:#141b30;border:1px solid #26304d;border-radius:8px;padding:6px 10px;font-size:12px}}
.ok{{color:#6ee7a2}} .n{{font-size:11.5px;color:#a8b3cf;margin:3px 0;line-height:1.4}}
.hd{{color:{theme};font-size:12px;margin:12px 0 4px;font-weight:700}}</style></head>
<body><div class=wrap>
<h1>{c['name']}</h1><div class=role>{c['role']}</div>
<div class=row>
 <div class=pill><span class=ok>● ONLINE</span></div>
 <div class=pill>backend: {ident['backend']}</div>
 <div class=pill>provider: {c['default_provider']}</div>
 <div class=pill>pid {os.getpid()}</div>
</div>
<div class=pill style='margin:6px 0'>HQ-hosted runtime · Claude blocked · {mem['total_lessons']} lessons</div>
<div class=hd>Latest notes</div>{notes or "<div class=n>(none yet)</div>"}
<div class=n style='margin-top:10px;color:#64748b'>ts {_utc()}</div>
</div></body></html>"""
                body = html.encode()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)
            else:
                self._send({"err": "not found"}, 404)
    return H

def serve(c: dict, port: int):
    srv = HTTPServer(("0.0.0.0", port), make_handler(c))
    print(f"[{c['name']}] runtime live pid={os.getpid()} port={port} backend=brain_router_non_claude")
    write_note(c, f"{c['name']} local runtime online (pid={os.getpid()}, port={port}, backend=brain_router_non_claude, Claude blocked).", kind="runtime_online")
    srv.serve_forever()

# ── smoke tester ──
def smoke(c: dict) -> dict:
    out = {"ceo": c["id"]}
    out["identity"] = load_identity(c)
    out["memory"] = read_memory(c, 2)
    out["note_write"] = write_note(c, f"{c['name']} smoke-test note (append-only).", kind="smoke")
    out["brain_router"] = brain_router_call(c, f"You are {c['name']}. Reply one word: {c['id'].upper()}OK", task="chat")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceo", required=True)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--whoami", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    c = cfg(a.ceo)
    if a.whoami: print(json.dumps(load_identity(c), indent=1)); return
    if a.smoke:  print(json.dumps(smoke(c), indent=1)); return
    if a.serve:  serve(c, a.port or c["port"]); return
    ap.error("choose --serve | --whoami | --smoke")

if __name__ == "__main__":
    main()
