#!/usr/bin/env python3
"""qsb_provider_agent.py — bounded multi-turn provider-side worker agent.

Authorized by CLAUDE.md 2026-06-14 section "bounded provider-side worker
agents". Reads gate from data/registries/qsb_provider_agentic_gate.json
and refuses to run unless enabled=true.

Hard caps (also enforced):
  per-turn cost <= per_turn_cap_usd
  cumulative session cost <= per_session_cap_usd
  turn_count <= max_turns_per_session
  spent_today + this-session <= daily_budget_usd
  tools whitelisted (refuses everything else)

Usage:
    python3 tools/qsb_provider_agent.py \
        --provider openai --model gpt-4o-mini \
        --system "You are Wren-junior, a tower auditor." \
        --task "Audit floors 40-45, return punch list" \
        [--session-id abc123]

    python3 tools/qsb_provider_agent.py --status
"""

from __future__ import annotations
import argparse, datetime, json, os, sys, subprocess, urllib.request, uuid
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
VAULT = ROOT / "floors/floor_28_security_department/vault"
GATE = REG / "qsb_provider_agentic_gate.json"
SESS = REG / "qsb_provider_agent_sessions.jsonl"
ACTIVITY = REG / "qsb_tower_activity_tail.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
SPEND_LEDGER = REG / "qsb_provider_spend_ledger.jsonl"

PRICING = {
    "openai": {
        "gpt-4o-mini":   {"input": 0.15, "output": 0.60},
        "gpt-4o":        {"input": 2.50, "output": 10.00},
        "gpt-4.1-mini":  {"input": 0.40, "output": 1.60},
    },
    "deepseek": {
        "deepseek-chat":     {"input": 0.27, "output": 1.10},
        "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    },
    # Local provider via Ollama — $0/token (Ross 2026-06-19 added Hermes
    # as a LOCAL agent option; budget caps still computed but always 0).
    "ollama": {
        "hermes3:8b":          {"input": 0.0, "output": 0.0},
        "hermes3:70b":         {"input": 0.0, "output": 0.0},
        "qwen2.5:7b-instruct": {"input": 0.0, "output": 0.0},
        "qwen2.5-coder:7b-instruct": {"input": 0.0, "output": 0.0},
        "nous-hermes2:10.7b":  {"input": 0.0, "output": 0.0},
    },
}

ENDPOINT = {
    "openai":   "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    # Ollama exposes an OpenAI-compatible /v1/chat/completions endpoint.
    "ollama":   "http://127.0.0.1:11434/v1/chat/completions",
}

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


# ── gate + budget enforcement ──────────────────────────────────────────

def load_gate() -> dict:
    if not GATE.exists():
        raise SystemExit("FATAL: provider_agentic_gate.json missing — gate locked")
    g = json.loads(GATE.read_text())
    if not g.get("enabled"):
        raise SystemExit("FATAL: provider_agentic_gate.enabled=false — kill switch ON")
    return g

def spent_today_usd() -> float:
    if not SPEND_LEDGER.exists(): return 0.0
    total = 0.0
    today = today_utc()
    for line in SPEND_LEDGER.read_text().splitlines():
        try:
            row = json.loads(line)
            if row.get("ts","")[:10] == today and row.get("kind") == "agentic":
                total += float(row.get("cost_usd", 0.0))
        except Exception:
            continue
    return total

def stamp_spend(cost_usd: float, provider: str, model: str, session_id: str, turn: int):
    row = {"ts": now_iso(), "kind": "agentic", "session_id": session_id,
           "provider": provider, "model": model, "turn": turn, "cost_usd": round(cost_usd,6)}
    with SPEND_LEDGER.open("a") as f: f.write(json.dumps(row)+"\n")

def stamp_session(payload: dict):
    with SESS.open("a") as f: f.write(json.dumps(payload)+"\n")
    with ACTIVITY.open("a") as f:
        f.write(json.dumps({"ts": payload["ts_end"], "event_kind": "provider_agent_session",
                            "summary": f"{payload['provider']}/{payload['model']} sess={payload['session_id'][:8]} turns={payload['turns']} cost=${payload['total_cost_usd']:.4f}",
                            "payload": payload})+"\n")
    with F47.open("a") as f:
        f.write(json.dumps({"ts": payload["ts_end"], "kind": "provider_agent_session",
                            "operator": "wren_provider_agent",
                            "summary": f"session {payload['session_id'][:8]} {payload['provider']}/{payload['model']} {payload['turns']} turns ${payload['total_cost_usd']:.4f}",
                            "task": payload.get("task","")[:240]})+"\n")


# ── tool implementations (whitelist) ───────────────────────────────────

def tool_qsb_read_registry(args: dict) -> str:
    rel = args.get("path","")
    if not rel or ".." in rel: return "ERROR: bad path"
    p = REG / rel.lstrip("/")
    if not p.exists(): return f"ERROR: not found: {rel}"
    if not str(p.resolve()).startswith(str(REG.resolve())):
        return "ERROR: escape attempt blocked"
    txt = p.read_text(errors="replace")
    if len(txt) > 20000: txt = txt[:20000] + "\n[truncated at 20000 chars]"
    return txt

def tool_qsb_read_floor_card(args: dict) -> str:
    n = args.get("floor")
    if n is None: return "ERROR: floor required"
    matches = list(ROOT.glob(f"floors/floor_{n}_*/floor_card.json"))
    if not matches: return f"ERROR: no floor_card.json for floor_{n}"
    return matches[0].read_text(errors="replace")[:20000]

def tool_qsb_grep_repo(args: dict) -> str:
    pat = args.get("pattern","")
    if not pat or len(pat) > 200: return "ERROR: pattern missing or too long"
    try:
        out = subprocess.run(
            ["rg", "-n", "--max-count", "5", "--max-columns", "200", pat, str(ROOT)],
            capture_output=True, text=True, timeout=15)
        result = (out.stdout or out.stderr)[:8000]
        return result or "(no matches)"
    except FileNotFoundError:
        return "ERROR: ripgrep not installed"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout"

def tool_qsb_propose_patch(args: dict) -> str:
    target = args.get("target_file","")
    body = args.get("patch_body","")
    if not target or not body: return "ERROR: target_file and patch_body required"
    pid = f"pa_{uuid.uuid4().hex[:10]}"
    proposals = REG / "qsb_proposal_queue.jsonl"
    row = {"ts": now_iso(), "proposal_id": pid, "source": "provider_agent",
           "target_file": target, "patch_body": body[:8000], "status": "queued_unsigned"}
    with proposals.open("a") as f: f.write(json.dumps(row)+"\n")
    return f"queued proposal_id={pid} (needs sandbox + 3 sigs)"

def tool_qsb_stamp_f47_record(args: dict) -> str:
    kind = args.get("kind","provider_agent_note")
    summary = args.get("summary","")[:500]
    rec = {"ts": now_iso(), "kind": kind, "operator": "provider_agent",
           "summary": summary, "via": "qsb_provider_agent"}
    with F47.open("a") as f: f.write(json.dumps(rec)+"\n")
    return f"stamped F47 {kind}"

TOOL_FNS = {
    "qsb_read_registry":    tool_qsb_read_registry,
    "qsb_read_floor_card":  tool_qsb_read_floor_card,
    "qsb_grep_repo":        tool_qsb_grep_repo,
    "qsb_propose_patch":    tool_qsb_propose_patch,
    "qsb_stamp_f47_record": tool_qsb_stamp_f47_record,
}

TOOL_DEFS = [
    {"type":"function","function":{
        "name":"qsb_read_registry","description":"Read a file under data/registries/. Returns text (capped 20k chars).",
        "parameters":{"type":"object","properties":{"path":{"type":"string","description":"relative path inside data/registries/"}},"required":["path"]}}},
    {"type":"function","function":{
        "name":"qsb_read_floor_card","description":"Read floors/floor_<N>_*/floor_card.json.",
        "parameters":{"type":"object","properties":{"floor":{"type":"integer"}},"required":["floor"]}}},
    {"type":"function","function":{
        "name":"qsb_grep_repo","description":"Ripgrep across the repo. Read-only.",
        "parameters":{"type":"object","properties":{"pattern":{"type":"string"}},"required":["pattern"]}}},
    {"type":"function","function":{
        "name":"qsb_propose_patch","description":"Queue a proposal for the bench. Needs sandbox + 3 sigs to apply.",
        "parameters":{"type":"object","properties":{"target_file":{"type":"string"},"patch_body":{"type":"string"}},"required":["target_file","patch_body"]}}},
    {"type":"function","function":{
        "name":"qsb_stamp_f47_record","description":"Append an audit row to F47 team records.",
        "parameters":{"type":"object","properties":{"kind":{"type":"string"},"summary":{"type":"string"}},"required":["summary"]}}},
]


# ── provider call ──────────────────────────────────────────────────────

def load_key(provider: str) -> str:
    # Local Ollama needs no auth — it's listening on 127.0.0.1.
    if provider == "ollama":
        return "local"
    p = VAULT / f".env.{provider}"
    if not p.exists(): raise SystemExit(f"FATAL: vault key missing: .env.{provider}")
    for line in p.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k,v = line.split("=",1)
            if "KEY" in k.upper() or "TOKEN" in k.upper():
                return v.strip().strip('"').strip("'")
    raise SystemExit(f"FATAL: no key parsed from .env.{provider}")

def cost_of(provider: str, model: str, in_toks: int, out_toks: int) -> float:
    p = PRICING.get(provider,{}).get(model)
    if not p: return 0.0
    return (in_toks * p["input"] + out_toks * p["output"]) / 1_000_000

def call_provider(provider: str, model: str, messages: list, tools: list) -> dict:
    body = {"model": model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.2}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(ENDPOINT[provider], data=data, method="POST")
    req.add_header("Content-Type","application/json")
    req.add_header("Authorization", f"Bearer {load_key(provider)}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── session runner ─────────────────────────────────────────────────────

def run_session(provider: str, model: str, system: str, task: str,
                 session_id: str = None, allowed_tools: list | None = None) -> dict:
    g = load_gate()
    if provider not in g["providers"]:
        raise SystemExit(f"FATAL: provider {provider} not whitelisted")
    if model not in PRICING.get(provider,{}):
        raise SystemExit(f"FATAL: model {model} not priced — refusing")

    # Per-role tool filter. None or [] means "no tools at all" only when
    # the caller passed an empty list explicitly; None means default (all).
    if allowed_tools is None:
        tool_defs = TOOL_DEFS
    else:
        allowed = set(allowed_tools)
        tool_defs = [td for td in TOOL_DEFS
                     if td["function"]["name"] in allowed]

    cap_session = float(g["per_session_cap_usd"])
    cap_turn = float(g["per_turn_cap_usd"])
    cap_day = float(g["daily_budget_usd"])
    max_turns = int(g["max_turns_per_session"])

    spent_pre = spent_today_usd()
    if spent_pre >= cap_day:
        raise SystemExit(f"FATAL: daily cap reached ${spent_pre:.4f}/${cap_day:.2f}")

    sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
    ts_start = now_iso()

    messages = [
        {"role":"system","content": system + "\n\nYou have a tool-use whitelist. Use tools sparingly — every turn costs money. Return your final answer as plain text when done."},
        {"role":"user","content": task},
    ]
    session_cost = 0.0
    tool_call_log = []
    final_text = ""

    for turn in range(1, max_turns+1):
        try:
            resp = call_provider(provider, model, messages, tool_defs)
        except Exception as e:
            return _close_session(sid, ts_start, provider, model, task, turn-1, session_cost, tool_call_log, f"ERROR: provider call failed: {e}")

        usage = resp.get("usage",{})
        in_t = usage.get("prompt_tokens",0)
        out_t = usage.get("completion_tokens",0)
        turn_cost = cost_of(provider, model, in_t, out_t)
        stamp_spend(turn_cost, provider, model, sid, turn)
        session_cost += turn_cost

        if turn_cost > cap_turn:
            return _close_session(sid, ts_start, provider, model, task, turn, session_cost, tool_call_log,
                                  f"BLOCKED: turn {turn} cost ${turn_cost:.4f} > cap ${cap_turn}")
        if session_cost > cap_session:
            return _close_session(sid, ts_start, provider, model, task, turn, session_cost, tool_call_log,
                                  f"BLOCKED: session cost ${session_cost:.4f} > cap ${cap_session}")
        if spent_pre + session_cost > cap_day:
            return _close_session(sid, ts_start, provider, model, task, turn, session_cost, tool_call_log,
                                  f"BLOCKED: daily cap would be exceeded")

        msg = resp["choices"][0]["message"]
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            final_text = msg.get("content","") or ""
            return _close_session(sid, ts_start, provider, model, task, turn, session_cost, tool_call_log, final_text)

        for tc in tool_calls:
            fn = tc["function"]["name"]
            try: args = json.loads(tc["function"]["arguments"] or "{}")
            except Exception: args = {}
            if fn not in TOOL_FNS:
                tool_result = f"ERROR: tool '{fn}' not in whitelist"
            else:
                try: tool_result = TOOL_FNS[fn](args)
                except Exception as e: tool_result = f"ERROR: {e}"
            tool_call_log.append({"turn": turn, "fn": fn, "args": args, "result_len": len(tool_result)})
            messages.append({"role":"tool","tool_call_id":tc["id"],"content":tool_result[:8000]})

    return _close_session(sid, ts_start, provider, model, task, max_turns, session_cost, tool_call_log,
                          f"max turns ({max_turns}) reached without final answer")

def _close_session(sid, ts_start, provider, model, task, turns, cost, tool_log, final_text) -> dict:
    payload = {
        "session_id": sid, "ts_start": ts_start, "ts_end": now_iso(),
        "provider": provider, "model": model, "task": task,
        "turns": turns, "total_cost_usd": round(cost,6),
        "tool_calls": tool_log, "final_text": final_text[:8000],
    }
    stamp_session(payload)
    return payload


# ── status + main ──────────────────────────────────────────────────────

def cmd_status():
    g = load_gate() if GATE.exists() else None
    spent = spent_today_usd()
    cap = float(g.get("daily_budget_usd", 0)) if g else 0
    print(f"gate enabled       : {g.get('enabled') if g else 'NO GATE FILE'}")
    print(f"daily cap (USD)    : ${cap:.2f}")
    print(f"spent today (USD)  : ${spent:.4f}")
    print(f"remaining today    : ${(cap - spent):.4f}")
    print(f"per-session cap    : ${g.get('per_session_cap_usd',0):.2f}")
    print(f"per-turn cap       : ${g.get('per_turn_cap_usd',0):.2f}")
    print(f"max turns          : {g.get('max_turns_per_session',0)}")
    print(f"providers          : {g.get('providers',[])}")
    print(f"tools whitelisted  : {g.get('tools_whitelist',[])}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--system", default="You are Wren-junior, an advisory worker on the QSB Tower. Use tools sparingly. Return concise findings.")
    ap.add_argument("--task", default=None)
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--allowed-tools", default=None,
                     help="comma-sep list of tools this session may call "
                          "(empty string = no tools at all)")
    a = ap.parse_args()

    if a.status: cmd_status(); return
    if not a.task:
        print("ERROR: --task required (or --status)"); sys.exit(2)

    # None = default (all tools). "" or "none" = no tools. CSV = whitelist.
    if a.allowed_tools is None:
        allowed = None
    elif a.allowed_tools.strip().lower() in ("", "none"):
        allowed = []
    else:
        allowed = [t.strip() for t in a.allowed_tools.split(",") if t.strip()]

    out = run_session(a.provider, a.model, a.system, a.task, a.session_id, allowed)
    print("━"*60)
    print(f"  session {out['session_id'][:12]}  {out['provider']}/{out['model']}")
    print(f"  turns={out['turns']}  cost=${out['total_cost_usd']:.4f}  tool_calls={len(out['tool_calls'])}")
    print("━"*60)
    print(out["final_text"])
    print("━"*60)

if __name__ == "__main__":
    main()
