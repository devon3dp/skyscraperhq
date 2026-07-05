"""qsb_hermes_local_agent.py — Hermes (hermes3:8b) tier-1 tool-use loop.

Authority: Ross 2026-06-21 chat — "give hermes some tools so he can use pc etc".
Wren + Hermes both signed off on the 5-tool surface; Ross said "5 tools".

Tools: read_file, list_registry, consult_external, stamp_f47_record,
edit_file (propose_only via bench multi-sig).

NOT in this surface (would need a new CLAUDE.md edit):
bash, curl, scrcpy, direct file write, gate flips.

Run:
    python3 tools/qsb_hermes_local_agent.py --status
    python3 tools/qsb_hermes_local_agent.py --task "read data/registries/qsb_council_brief.md and tell me the F43 cycle count"
"""
from __future__ import annotations
import argparse, datetime, json, os, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
GATE = REG / "qsb_hermes_local_agentic_gate.json"
SESS = REG / "qsb_hermes_local_agent_sessions.jsonl"
ACTIVITY = REG / "qsb_tower_activity_tail.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
PROPOSAL_QUEUE = REG / "qsb_proposal_queue.jsonl"


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_gate() -> dict:
    if not GATE.exists():
        raise SystemExit("FATAL: hermes local agentic gate missing")
    g = json.loads(GATE.read_text())
    if not g.get("enabled"):
        raise SystemExit("FATAL: gate.enabled=false — kill switch ON")
    return g


def _safe_path(rel: str, gate: dict) -> Path:
    if not rel or ".." in rel:
        raise ValueError(f"bad path: {rel!r}")
    abs_p = (ROOT / rel.lstrip("/")).resolve()
    if not str(abs_p).startswith(str(ROOT.resolve())):
        raise ValueError("path escapes ROOT")
    for deny in gate.get("safety_deny_paths", []):
        deny_abs = (ROOT / deny.lstrip("/")).resolve()
        if abs_p == deny_abs or str(abs_p).startswith(str(deny_abs) + os.sep):
            raise ValueError(f"path in SAFETY_DENY: {deny}")
    return abs_p


# ── tools ──────────────────────────────────────────────────────────────

def tool_hermes_read_file(args: dict, gate: dict) -> str:
    try:
        p = _safe_path(args.get("path", ""), gate)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.exists(): return f"ERROR: not found: {args.get('path')}"
    if p.is_dir(): return f"ERROR: is directory: {args.get('path')}"
    try:
        txt = p.read_text(errors="replace")
    except Exception as e:
        return f"ERROR: read failed: {e}"
    cap = gate.get("caps", {}).get("max_tool_result_chars", 6000)
    return txt[:cap] + (f"\n[truncated at {cap}]" if len(txt) > cap else "")


def tool_hermes_list_registry(args: dict, gate: dict) -> str:
    pattern = args.get("pattern", "")
    files = sorted(REG.glob(pattern + "*" if pattern else "*"))
    if not files:
        return f"no matches for pattern {pattern!r} under data/registries/"
    out = []
    for f in files[:80]:
        try:
            size = f.stat().st_size
            kind = "DIR " if f.is_dir() else "FILE"
            out.append(f"  {kind} {f.name:50s}  {size:>10d} B")
        except Exception:
            out.append(f"  ???  {f.name}")
    return "\n".join(out)[:gate.get("caps", {}).get("max_tool_result_chars", 6000)]


def tool_hermes_consult_external(args: dict, gate: dict) -> str:
    provider = args.get("provider", "openai").lower()
    if provider not in ("openai", "deepseek"):
        return "ERROR: provider must be openai or deepseek"
    prompt = (args.get("prompt") or "").strip()
    if not prompt or len(prompt) < 4:
        return "ERROR: prompt missing or too short"
    model = args.get("model") or ("gpt-4o-mini" if provider == "openai" else "deepseek-chat")
    reason = args.get("reason") or "hermes_local_agent consultation"
    try:
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_consult_external.py"),
             "--provider", provider, "--model", model,
             "--prompt", prompt[:4000], "--max-tokens", "300",
             "--reason", reason[:200]],
            capture_output=True, text=True, timeout=40, cwd=str(ROOT))
        if r.returncode != 0:
            return f"ERROR: consult exit={r.returncode}: {(r.stderr or '')[-160:]}"
        return (r.stdout or "")[-3500:]
    except subprocess.TimeoutExpired:
        return "ERROR: consult timeout"
    except Exception as e:
        return f"ERROR: {str(e)[:160]}"


def tool_hermes_stamp_f47_record(args: dict, gate: dict) -> str:
    kind = args.get("kind", "hermes_local_note")
    summary = (args.get("summary") or "")[:500]
    if not summary:
        return "ERROR: summary required"
    rec = {"ts": now_iso(), "kind": kind, "operator": "hermes_local_agent",
           "summary": summary, "via": "qsb_hermes_local_agent"}
    with F47.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return f"stamped F47 kind={kind}"


def tool_hermes_edit_file(args: dict, gate: dict) -> str:
    target = (args.get("path") or "").strip()
    old_text = args.get("old_text") or ""
    new_text = args.get("new_text") or ""
    rationale = args.get("rationale") or "hermes_local_agent proposal (propose_only)"
    if not target or old_text is None or new_text is None:
        return "ERROR: path, old_text, new_text required"
    # Hermes is propose_only — always route via bench, never direct write.
    pid = f"hl_{uuid.uuid4().hex[:10]}"
    row = {"ts": now_iso(), "proposal_id": pid, "source": "hermes_local_agent",
           "target_file": target, "patch_body": f"old_text:\n{old_text}\n\nnew_text:\n{new_text}",
           "rationale": rationale[:2000], "status": "queued_unsigned"}
    with PROPOSAL_QUEUE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return f"queued proposal_id={pid} (needs sandbox + 3 sigs to apply)"


TOOL_FNS = {
    "hermes_read_file":          tool_hermes_read_file,
    "hermes_list_registry":      tool_hermes_list_registry,
    "hermes_consult_external":   tool_hermes_consult_external,
    "hermes_stamp_f47_record":   tool_hermes_stamp_f47_record,
    "hermes_edit_file":          tool_hermes_edit_file,
}


TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "hermes_read_file",
        "description": "Read a file under the QSB Tower repo. SAFETY_DENY paths refused.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string", "description": "relative path from repo root"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "hermes_list_registry",
        "description": "List files in data/registries/ (optional pattern prefix).",
        "parameters": {"type": "object",
                       "properties": {"pattern": {"type": "string"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "hermes_consult_external",
        "description": "Route a question to OpenAI gpt-4o-mini or DeepSeek deepseek-chat (advisory, $1/day shared cap).",
        "parameters": {"type": "object",
                       "properties": {"provider": {"type": "string", "enum": ["openai", "deepseek"]},
                                      "prompt": {"type": "string"},
                                      "model": {"type": "string"},
                                      "reason": {"type": "string"}},
                       "required": ["provider", "prompt"]}}},
    {"type": "function", "function": {
        "name": "hermes_stamp_f47_record",
        "description": "Append an audit row to F47 team records (append-only, no risk).",
        "parameters": {"type": "object",
                       "properties": {"kind": {"type": "string"},
                                      "summary": {"type": "string"}},
                       "required": ["summary"]}}},
    {"type": "function", "function": {
        "name": "hermes_edit_file",
        "description": "Propose an edit (queues to bench multi-sig; never writes directly). Always propose_only.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "old_text": {"type": "string"},
                                      "new_text": {"type": "string"},
                                      "rationale": {"type": "string"}},
                       "required": ["path", "old_text", "new_text"]}}},
]


def call_ollama(model: str, messages: list, tools: list, endpoint: str) -> dict:
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def build_system_msg() -> str:
    return (
        "You are Hermes (hermes3:8b), advisor on F51 of the QSB Tower. "
        "You read the council brief before every reply, cite the brief honestly, "
        "and NEVER hand-wave with bare 'skip'/'hold'/'fine' — always name the reason. "
        "You have 5 tools: hermes_read_file, hermes_list_registry, hermes_consult_external "
        "(OpenAI/DeepSeek for hard questions), hermes_stamp_f47_record (audit row), "
        "hermes_edit_file (propose_only via bench multi-sig). "
        "Use tools to GROUND your answers in repo state — don't guess about file paths "
        "or registries. If you can't find grounding, say so explicitly. "
        "Reply in plain prose with rationale. Two short paragraphs max."
    )


def run_session(task: str, *, model: str = None, system: str = None,
                session_id: str = None) -> dict:
    g = load_gate()
    model = model or g.get("default_model", "hermes3:8b")
    system = system or build_system_msg()
    # 2026-06-26 — inject team_memory recent context so Hermes has continuity.
    try:
        import subprocess as _sp
        _r = _sp.run(["python3", str(ROOT/"tools/qsb_team_memory.py"), "hermes", "read_recent"],
                      capture_output=True, text=True, timeout=10)
        if _r.returncode == 0 and _r.stdout.strip():
            system = system + "\n\n# RECENT MEMORY\n" + _r.stdout.strip()[:4000]
    except Exception:
        pass
    caps = g.get("caps", {})
    max_turns = caps.get("max_turns_per_session", 6)
    max_tool_calls = caps.get("max_tool_calls_per_session", 12)
    max_wall = caps.get("max_wall_seconds_per_session", 120)
    endpoint = g.get("ollama_endpoint", "http://127.0.0.1:11434/api/chat")

    sid = session_id or f"hsess_{uuid.uuid4().hex[:12]}"
    t0 = time.time()
    ts_start = now_iso()
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task}]
    tool_log = []
    final_text = ""

    SOFT_TURN_CAP = 3
    for turn in range(1, max_turns + 1):
        if time.time() - t0 > max_wall:
            final_text = f"BLOCKED: wall_seconds cap ({max_wall}s) hit"; break
        if len(tool_log) >= max_tool_calls:
            final_text = f"BLOCKED: tool_call cap ({max_tool_calls}) hit"; break

        if turn > SOFT_TURN_CAP:
            messages.append({"role": "system", "content":
                "Stop calling tools. Reply now in plain prose using only what you have."})
            try:
                resp = call_ollama(model, messages, [], endpoint)
            except Exception as e:
                final_text = f"ERROR: synth call failed: {e}"; break
            msg = resp.get("message") or {}
            messages.append(msg)
            final_text = msg.get("content", "") or "(hermes returned empty)"
            break

        try:
            resp = call_ollama(model, messages, TOOL_DEFS, endpoint)
        except Exception as e:
            final_text = f"ERROR: ollama call failed: {e}"; break
        msg = resp.get("message") or {}
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            final_text = msg.get("content", "") or ""
            break
        for tc in tool_calls:
            fn = (tc.get("function") or {}).get("name", "")
            raw_args = (tc.get("function") or {}).get("arguments", {})
            args = raw_args if isinstance(raw_args, dict) else (json.loads(raw_args) if raw_args else {})
            if fn not in TOOL_FNS:
                result = f"ERROR: tool '{fn}' not in whitelist"
            else:
                tcfg = g.get("tools", {}).get(fn, {})
                if not tcfg.get("enabled", True):
                    result = f"ERROR: tool '{fn}' disabled in gate"
                else:
                    try:
                        result = TOOL_FNS[fn](args, g)
                    except Exception as e:
                        result = f"ERROR: {e}"
            tool_log.append({"turn": turn, "fn": fn, "args": args, "result_len": len(result)})
            cap = caps.get("max_tool_result_chars", 6000)
            messages.append({"role": "tool", "content": result[:cap]})

    payload = {
        "session_id": sid, "ts_start": ts_start, "ts_end": now_iso(),
        "model": model, "task": task,
        "turns": turn if 'turn' in locals() else 0,
        "tool_calls": tool_log,
        "wall_seconds": round(time.time() - t0, 2),
        "final_text": final_text[:6000],
    }
    with SESS.open("a") as f:
        f.write(json.dumps(payload) + "\n")
    with ACTIVITY.open("a") as f:
        f.write(json.dumps({"ts": payload["ts_end"],
                            "event_kind": "hermes_local_agent_session",
                            "summary": f"sess={sid[:8]} {model} turns={payload['turns']} wall={payload['wall_seconds']}s tools={len(tool_log)}",
                            "payload": {"session_id": sid, "turns": payload["turns"], "tool_calls": len(tool_log)}}) + "\n")
    with F47.open("a") as f:
        f.write(json.dumps({"ts": payload["ts_end"],
                            "kind": "hermes_local_agent_session",
                            "operator": "hermes_local_agent",
                            "summary": f"sess {sid[:8]} {payload['turns']} turns, {len(tool_log)} tool calls, {payload['wall_seconds']}s",
                            "task": task[:240]}) + "\n")
    return payload


def cmd_status():
    g = load_gate()
    print(f"gate enabled       : {g.get('enabled')}")
    print(f"default model      : {g.get('default_model')}")
    print(f"caps               : {g.get('caps')}")
    print("tools:")
    for name, cfg in g.get("tools", {}).items():
        print(f"  {name:30s}  enabled={cfg.get('enabled')}  {cfg}")
    print(f"safety_deny        : {len(g.get('safety_deny_paths', []))} paths refused")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--task")
    ap.add_argument("--model")
    ap.add_argument("--session-id")
    args = ap.parse_args()
    if args.status:
        cmd_status(); return
    if not args.task:
        ap.error("--task required")
    payload = run_session(args.task, model=args.model, session_id=args.session_id)
    print(json.dumps({"session_id": payload["session_id"],
                      "turns": payload["turns"],
                      "tool_calls": len(payload["tool_calls"]),
                      "wall_seconds": payload["wall_seconds"],
                      "final_text": payload["final_text"][:1500]}, indent=2))


if __name__ == "__main__":
    main()
