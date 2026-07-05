#!/usr/bin/env python3
"""qsb_wren_local_agent.py — offline-Wren tier-2 tool-use loop.

Lets Wren-offline (qwen2.5:7b via Ollama) actually DO things — read files,
edit files (proposal-mode by default), bash (off by default), scrcpy phone,
curl (off by default). Mirrors qsb_provider_agent.py shape but points at
local Ollama instead of OpenAI/DeepSeek.

Authority: CLAUDE.md 2026-06-14 section authorizing bounded code mutation
via bench (maintenance_auto_repair_enabled) + offline-Wren scaffold.
Gate file: data/registries/qsb_wren_local_agentic_gate.json

Conservative defaults (Plan agent's risky-choice flags):
  · bash off — Ross flips when ready
  · edit_file = propose_only (queues bench proposal, no direct write)
  · scrcpy off, curl off, host_allowlist empty
  · all safety paths refused regardless of mode

Usage:
    python3 tools/qsb_wren_local_agent.py --status
    python3 tools/qsb_wren_local_agent.py --task "read floors/floor_47.../floor_card.json and summarize"
    python3 tools/qsb_wren_local_agent.py --task "grep TODO in src/tower and stamp an F47 note"
"""
from __future__ import annotations
import argparse, datetime, json, os, re, shlex, shutil, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
GATE = REG / "qsb_wren_local_agentic_gate.json"
SESS = REG / "qsb_wren_local_agent_sessions.jsonl"
ACTIVITY = REG / "qsb_tower_activity_tail.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
PROPOSAL_QUEUE = REG / "qsb_proposal_queue.jsonl"
MEMORY_INDEX = Path("/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/MEMORY.md")
DIARY = ROOT / "qsb_session_diary.md"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


# ── gate ───────────────────────────────────────────────────────────────

def load_gate() -> dict:
    if not GATE.exists():
        raise SystemExit("FATAL: wren local agentic gate missing")
    g = json.loads(GATE.read_text())
    if not g.get("enabled"):
        raise SystemExit("FATAL: gate.enabled=false — kill switch ON")
    return g


# ── path safety ────────────────────────────────────────────────────────

def _safe_path(rel_path: str, gate: dict, *, mode: str = "read") -> Path:
    """Resolve, contain to ROOT, refuse safety-deny prefixes.
    Returns absolute Path. Raises ValueError if not allowed."""
    if not rel_path or ".." in rel_path:
        raise ValueError(f"bad path: {rel_path!r}")
    rel = rel_path.lstrip("/")
    abs_p = (ROOT / rel).resolve()
    if not str(abs_p).startswith(str(ROOT.resolve())):
        raise ValueError("path escapes ROOT")
    for deny in gate.get("safety_deny_paths", []):
        deny_abs = (ROOT / deny.lstrip("/")).resolve()
        # match if path IS the deny target or inside a deny directory
        if abs_p == deny_abs or str(abs_p).startswith(str(deny_abs) + os.sep):
            raise ValueError(f"path is in SAFETY_DENY: {deny}")
    return abs_p


# ── tools ──────────────────────────────────────────────────────────────

def tool_wren_read_file(args: dict, gate: dict) -> str:
    try:
        p = _safe_path(args.get("path",""), gate, mode="read")
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.exists(): return f"ERROR: not found: {args['path']}"
    if p.is_dir(): return f"ERROR: is directory, not file: {args['path']}"
    try:
        txt = p.read_text(errors="replace")
    except Exception as e:
        return f"ERROR: read failed: {e}"
    cap = gate.get("caps",{}).get("max_tool_result_chars", 8000)
    if len(txt) > cap: txt = txt[:cap] + f"\n[truncated at {cap} chars]"
    return txt

def tool_wren_grep_repo(args: dict, gate: dict) -> str:
    pat = args.get("pattern","")
    if not pat or len(pat) > 200: return "ERROR: pattern missing or too long"
    path_filter = args.get("path", "")
    target = str(ROOT) if not path_filter else str(_safe_path(path_filter, gate, mode="read"))
    try:
        out = subprocess.run(
            ["rg", "-n", "--max-count", "8", "--max-columns", "200", pat, target],
            capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return "ERROR: ripgrep not installed"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout"
    result = (out.stdout or out.stderr or "(no matches)")
    cap = gate.get("caps",{}).get("max_tool_result_chars", 8000)
    return result[:cap]

def tool_wren_edit_file(args: dict, gate: dict) -> str:
    cfg = gate.get("tools",{}).get("wren_edit_file",{})
    if not cfg.get("enabled"): return "ERROR: wren_edit_file disabled in gate"
    target_rel = args.get("path","")
    old_text = args.get("old_text","")
    new_text = args.get("new_text","")
    if not target_rel or old_text is None or new_text is None:
        return "ERROR: path, old_text, new_text required"
    try:
        target = _safe_path(target_rel, gate, mode="write")
    except ValueError as e:
        # safety-denied → auto-route to propose_patch
        return tool_wren_propose_patch({
            "target_file": target_rel,
            "patch_body": f"# AUTO-CONVERTED from edit_file (safety-denied path)\nold_text:\n{old_text}\n\nnew_text:\n{new_text}",
            "rationale": f"path in SAFETY_DENY: {e}",
        }, gate)
    if cfg.get("mode","propose_only") == "propose_only":
        return tool_wren_propose_patch({
            "target_file": str(target.relative_to(ROOT)),
            "patch_body": f"old_text:\n{old_text}\n\nnew_text:\n{new_text}",
            "rationale": args.get("rationale", "wren_local_agent edit (propose_only mode)"),
        }, gate)
    # direct mode
    if not target.exists(): return f"ERROR: target not found: {target_rel}"
    if target.stat().st_size > 200_000: return "ERROR: file too large (>200k)"
    try:
        content = target.read_text(errors="replace")
    except Exception as e:
        return f"ERROR: read for edit failed: {e}"
    if content.count(old_text) != 1:
        return f"ERROR: old_text not unique (count={content.count(old_text)})"
    # 2026-07-03 Ross "she must always backup before she replaces anything" —
    # every direct edit auto-backs-up to _archive/wren_backups/<path>_<ts>.bak
    try:
        from datetime import datetime as _dt, timezone as _tz
        ts = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = ROOT / "_archive/wren_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        # flatten path into filename so nested paths don't collide
        flat_name = str(target.relative_to(ROOT)).replace("/", "__") + f".{ts}.bak"
        (backup_dir / flat_name).write_text(content)
        backup_ref = f"_archive/wren_backups/{flat_name}"
    except Exception as _e:
        return f"ERROR: backup failed (refusing to edit without backup): {_e}"
    new_content = content.replace(old_text, new_text, 1)
    tmp = target.with_suffix(target.suffix + ".wren_tmp")
    tmp.write_text(new_content)
    os.replace(tmp, target)
    return f"edited {target_rel} ({len(content)} → {len(new_content)} chars) · backup: {backup_ref}"

def tool_wren_write_file(args: dict, gate: dict) -> str:
    """2026-07-03 Ross training curriculum — creates or overwrites a file.
    Unlike wren_edit_file (which needs the file to exist + unique old_text),
    this lets Wren CREATE files from scratch. Auto-backup fires if the target
    already exists (same as edit)."""
    cfg = gate.get("tools",{}).get("wren_write_file",{"enabled": True, "mode": "direct"})
    if not cfg.get("enabled"): return "ERROR: wren_write_file disabled in gate"
    target_rel = args.get("path","")
    content = args.get("content","")
    if not target_rel: return "ERROR: path required"
    if content is None: return "ERROR: content required (can be empty string)"
    try:
        target = _safe_path(target_rel, gate, mode="write")
    except ValueError as e:
        return f"ERROR: {e}"
    if len(content) > 200_000: return "ERROR: content too large (>200k)"
    # Auto-backup if file exists
    backup_ref = "(no backup — new file)"
    if target.exists():
        try:
            from datetime import datetime as _dt, timezone as _tz
            ts = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = ROOT / "_archive/wren_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            flat = str(target.relative_to(ROOT)).replace("/", "__") + f".{ts}.bak"
            old = target.read_text(errors="replace")
            (backup_dir / flat).write_text(old)
            backup_ref = f"_archive/wren_backups/{flat}"
        except Exception as _e:
            return f"ERROR: backup failed: {_e}"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".wren_tmp")
    tmp.write_text(content)
    os.replace(tmp, target)
    return f"wrote {target_rel} ({len(content)} chars) · backup: {backup_ref}"


def tool_wren_bash(args: dict, gate: dict) -> str:
    cfg = gate.get("tools",{}).get("wren_bash",{})
    if not cfg.get("enabled"): return "ERROR: wren_bash disabled in gate"
    cmd = args.get("cmd","").strip()
    if not cmd: return "ERROR: cmd required"
    # 2026-07-03 Ross "give her freedom": if allowlist contains '*', bypass
    # binary check. Destructive regex below still enforced.
    try: first = shlex.split(cmd)[0]
    except Exception: return "ERROR: shell-parse failed"
    allow = set(cfg.get("binary_allowlist", []))
    if "*" not in allow and first not in allow:
        return f"ERROR: '{first}' not in binary_allowlist {sorted(allow)}"
    # extra deny regex
    if re.search(r"(\s|^)(rm\s|sudo|mv\s|dd\s|mkfs|chmod\s|chown\s|>\s*/|\|\s*sh|;\s*rm)", cmd):
        return "ERROR: dangerous pattern in cmd"
    timeout = min(int(args.get("timeout_s", 15)), 30)
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             timeout=timeout, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return "ERROR: timeout"
    cap = gate.get("caps",{}).get("max_tool_result_chars", 8000)
    return (out.stdout + ("\n[stderr]\n"+out.stderr if out.stderr else ""))[:cap]

def tool_wren_scrcpy(args: dict, gate: dict) -> str:
    cfg = gate.get("tools",{}).get("wren_scrcpy",{})
    if not cfg.get("enabled"): return "ERROR: wren_scrcpy disabled in gate"
    action = args.get("action","")
    if action not in cfg.get("action_allowlist", []):
        return f"ERROR: action '{action}' not in allowlist {cfg.get('action_allowlist',[])}"
    try:
        if action == "list_devices":
            out = subprocess.run(["adb","devices"], capture_output=True, text=True, timeout=10)
            return out.stdout
        if action == "screenshot":
            out_dir = ROOT / "data/wren_phone"
            out_dir.mkdir(exist_ok=True)
            outp = out_dir / f"screen_{int(time.time())}.png"
            subprocess.run(["adb","exec-out","screencap","-p"], stdout=outp.open("wb"), timeout=15)
            return f"saved {outp.relative_to(ROOT)} ({outp.stat().st_size} bytes)"
        if action == "tap":
            x = int(args.get("x",0)); y = int(args.get("y",0))
            if not (0 <= x <= 2200 and 0 <= y <= 2200): return "ERROR: tap out of bounds"
            subprocess.run(["adb","shell","input","tap",str(x),str(y)], timeout=5)
            return f"tapped {x},{y}"
    except Exception as e:
        return f"ERROR: scrcpy failed: {e}"
    return "ERROR: unknown action"

def tool_wren_curl(args: dict, gate: dict) -> str:
    cfg = gate.get("tools",{}).get("wren_curl",{})
    if not cfg.get("enabled"): return "ERROR: wren_curl disabled in gate"
    url = args.get("url","")
    method = (args.get("method") or "GET").upper()
    allowed_methods = cfg.get("methods") or ["GET"]
    if method not in allowed_methods:
        return f"ERROR: method '{method}' not in gate-allowed {allowed_methods}"
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    allow = cfg.get("host_allowlist", [])
    if host not in allow and "*" not in allow:
        return f"ERROR: host '{host}' not in allowlist {allow}"
    try:
        headers = {"User-Agent": "qsb-wren/1.0"}
        body_data = None
        if method == "POST":
            # Accept either {"body":"..."} (raw) or {"json":{...}} (serialised)
            if "json" in args:
                import json as _json
                body_data = _json.dumps(args["json"]).encode()
                headers["Content-Type"] = "application/json"
            elif "body" in args:
                body_data = str(args["body"]).encode()
                headers["Content-Type"] = args.get(
                    "content_type", "application/x-www-form-urlencoded")
        req = urllib.request.Request(url, data=body_data, method=method,
                                      headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return body[:16000]
    except Exception as e:
        return f"ERROR: curl failed: {e}"

def tool_wren_stamp_f47_record(args: dict, gate: dict) -> str:
    kind = args.get("kind","wren_local_note")
    summary = args.get("summary","")[:500]
    rec = {"ts": now_iso(), "kind": kind, "operator": "wren_local_agent",
           "summary": summary, "via": "qsb_wren_local_agent"}
    with F47.open("a") as f: f.write(json.dumps(rec) + "\n")
    return f"stamped F47 kind={kind}"

def tool_wren_retrieve(args: dict, gate: dict) -> str:
    """Tier-3 RAG: retrieve top-k chunks from the codebase index."""
    cfg = gate.get("tools",{}).get("wren_retrieve",{})
    if not cfg.get("enabled"): return "ERROR: wren_retrieve disabled in gate"
    query = (args.get("query","") or "").strip()
    if not query or len(query) > 500: return "ERROR: query missing or too long"
    k = int(args.get("k", 6))
    k = max(1, min(k, 10))
    try:
        sys.path.insert(0, str(ROOT/"tools"))
        from qsb_wren_rag import retrieve as _rag_retrieve  # type: ignore
    except Exception as e:
        return f"ERROR: import qsb_wren_rag failed: {e}"
    try:
        results = _rag_retrieve(query, k=k)
    except Exception as e:
        return f"ERROR: retrieve failed: {e}"
    if results and "error" in results[0]:
        return results[0]["error"]
    lines = []
    for r in results:
        lines.append(f"--- #{r['rank']} {r['path']}:{r['lines']} (score {r['score']:.3f}) ---")
        lines.append(r['text'])
    out = "\n".join(lines)
    cap = gate.get("caps",{}).get("max_tool_result_chars", 8000)
    return out[:cap]


def tool_wren_propose_patch(args: dict, gate: dict) -> str:
    target = args.get("target_file","")
    body = args.get("patch_body","")
    rationale = args.get("rationale","")
    if not target or not body: return "ERROR: target_file and patch_body required"
    pid = f"wl_{uuid.uuid4().hex[:10]}"
    row = {"ts": now_iso(), "proposal_id": pid, "source": "wren_local_agent",
           "target_file": target, "patch_body": body[:8000],
           "rationale": rationale[:2000], "status": "queued_unsigned"}
    with PROPOSAL_QUEUE.open("a") as f: f.write(json.dumps(row)+"\n")
    return f"queued proposal_id={pid} (needs sandbox + 3 sigs)"



def tool_wren_list_skills(args: dict, gate: dict) -> str:
    """Tier-4: list available skills with their description + safety class."""
    skills_dir = ROOT / "skills/wren"
    if not skills_dir.exists():
        return "no skills directory yet"
    out = []
    for d in sorted(skills_dir.iterdir()):
        manifest = d / "skill.json"
        if not manifest.exists(): continue
        try: m = json.loads(manifest.read_text())
        except Exception: continue
        out.append(f"  {m.get('name','?'):28s}  [{m.get('safety_class','?')}]  {m.get('description','')[:80]}")
    return "\n".join(out) or "(no skills)"


def tool_wren_run_skill(args: dict, gate: dict) -> str:
    """Tier-4: execute a skill by name with given params."""
    name = args.get("name","")
    params = args.get("params", {})
    if not name: return "ERROR: name required"
    skill_dir = ROOT / "skills/wren" / name
    manifest_p = skill_dir / "skill.json"
    skill_py = skill_dir / "skill.py"
    if not manifest_p.exists(): return f"ERROR: skill not found: {name}"
    try: manifest = json.loads(manifest_p.read_text())
    except Exception as e: return f"ERROR: bad manifest: {e}"
    safety = manifest.get("safety_class", "exec")
    # write skills queue to claude_signoff only for safety_class in {write, exec}
    if safety in ("write", "exec"):
        return f"ERROR: skill {name} has safety_class={safety} — must route through wren_propose_patch / claude_signoff"
    # safe (read/stamp) skills run directly
    sys.path.insert(0, str(skill_dir))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"wren_skill_{name}", skill_py)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        if not hasattr(mod, "run"): return "ERROR: skill missing run()"
        result = mod.run(**params)
    except TypeError as e:
        return f"ERROR: param mismatch: {e}"
    except Exception as e:
        return f"ERROR: skill raised: {e}"
    return json.dumps(result, default=str)[:8000]


TOOL_FNS = {
    "wren_read_file":        tool_wren_read_file,
    "wren_grep_repo":        tool_wren_grep_repo,
    "wren_retrieve":         tool_wren_retrieve,
    "wren_edit_file":        tool_wren_edit_file,
    "wren_write_file":       tool_wren_write_file,
    "wren_bash":             tool_wren_bash,
    "wren_scrcpy":           tool_wren_scrcpy,
    "wren_curl":             tool_wren_curl,
    "wren_stamp_f47_record": tool_wren_stamp_f47_record,
    "wren_propose_patch":    tool_wren_propose_patch,
    "wren_list_skills":      tool_wren_list_skills,
    "wren_run_skill":        tool_wren_run_skill,
    "wren_ask_airllm":       lambda args, gate: _tool_wren_ask_airllm(args, gate),
    "wren_dispatch_f46_team": lambda args, gate: _tool_wren_dispatch_f46_team(args, gate),
    "wren_notification":     lambda args, gate: _tool_wren_notification(args, gate),
    "wren_monitor":          lambda args, gate: _tool_wren_monitor(args, gate),
    "wren_test_runner":      lambda args, gate: _tool_wren_test_runner(args, gate),
    "wren_database_query":   lambda args, gate: _tool_wren_database_query(args, gate),
    "wren_deploy":           lambda args, gate: _tool_wren_deploy(args, gate),
    "wren_message_claude":   lambda args, gate: _tool_wren_message_claude(args, gate),
    "wren_dispatch_hermes":  lambda args, gate: _tool_wren_dispatch_peer("hermes", args, gate),
    "wren_dispatch_iquest":  lambda args, gate: _tool_wren_dispatch_peer("iquest", args, gate),
}


def _tool_wren_dispatch_peer(peer: str, args: dict, gate: dict) -> str:
    """2026-07-03 Ross: 'wren can use hermes and iquest'. Fire a peer local
    agent (hermes/iquest) with a single task, return final_text."""
    task = args.get("task", "")
    if not task or len(task) < 4:
        return "ERROR: task required (min 4 chars)"
    peer_agents = {
        "hermes": ROOT / "tools/qsb_hermes_local_agent.py",
        "iquest": ROOT / "tools/qsb_iquest_local_agent.py",
    }
    agent_path = peer_agents.get(peer)
    if not agent_path or not agent_path.exists():
        return f"ERROR: {peer} local agent not available"
    try:
        r = subprocess.run(
            ["python3", str(agent_path), "--task", task[:2000]],
            capture_output=True, text=True, timeout=180)
        try:
            j = json.loads(r.stdout or "")
            return (j.get("final_text") or "").strip()[:1500] or f"({peer} empty)"
        except Exception:
            return (r.stdout or "")[-1500:] or f"({peer} no output)"
    except subprocess.TimeoutExpired:
        return f"({peer} timeout at 180s)"
    except Exception as e:
        return f"({peer} err: {e})"


def _tool_wren_dispatch_f46_team(args: dict, gate: dict) -> str:
    """Fire Wren's own F46 team (architect/builder/decorator) on a task.
    Each member is a separate Ollama call with a role-specific persona.
    Returns the 3 short proposals concatenated so Wren can synthesize."""
    task = args.get("task", "")
    if not task or len(task) < 8:
        return "ERROR: task too short"
    member = args.get("member", "all")
    try:
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_f46_wren_team.py"),
             "--task", task[:600],
             "--member", member, "--quiet"],
            capture_output=True, text=True, timeout=80, cwd=str(ROOT))
        if r.returncode != 0:
            return f"ERROR: team dispatch exit={r.returncode}: {(r.stderr or '')[-160:]}"
        # Read last 3 rows of qsb_f46_team_runs.jsonl for the replies
        runs = ROOT / "data/registries/qsb_f46_team_runs.jsonl"
        if not runs.exists():
            return "ERROR: no team runs log"
        rows = [json.loads(l) for l in runs.read_text().splitlines()[-3:] if l.strip()]
        out = []
        for row in rows:
            out.append(f"{row.get('member','?')}: {(row.get('reply') or '')[:600]}")
        return "\n\n".join(out)[:4000]
    except subprocess.TimeoutExpired:
        return "ERROR: team timeout"
    except Exception as e:
        return f"ERROR: {str(e)[:200]}"


def _tool_wren_ask_airllm(args: dict, gate: dict) -> str:
    """F23 AirLLM bridge — Wren reaches a bigger model when qwen2.5:7b
    runs out of depth. One call per session, model from allowlist."""
    cfg = gate.get("tools", {}).get("wren_ask_airllm", {})
    if not cfg.get("enabled", True):
        return "ERROR: wren_ask_airllm disabled in gate"
    prompt = args.get("prompt", "")
    if not prompt or len(prompt) < 8:
        return "ERROR: prompt too short"
    model = args.get("model", "Qwen/Qwen2.5-32B-Instruct")
    try:
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_airllm_ask.py"),
             "--model", model, "--prompt", prompt[:4000],
             "--max-new", str(int(args.get("max_new", 256))),
             "--timeout", "240"],
            capture_output=True, text=True, timeout=260, cwd=str(ROOT))
        if r.returncode != 0:
            return f"ERROR: airllm call exit={r.returncode}: {(r.stderr or '')[-200:]}"
        try:
            d = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            d = {"ok": False, "raw": (r.stdout or "")[-300:]}
        if not d.get("ok"):
            return f"ERROR: airllm: {d.get('error','?')}"
        return f"[{model} · wall={d.get('wall_s','?')}s] {d.get('reply','')[:3000]}"
    except subprocess.TimeoutExpired:
        return "ERROR: airllm wrapper timeout"
    except Exception as e:
        return f"ERROR: {str(e)[:200]}"


def _tool_wren_message_claude(args: dict, gate: dict) -> str:
    """Append a note to the Claude/Wren helix bridge so Claude sees it on his
    next main-loop tick. One-way from Wren's side — Claude reads the bridge
    via his usual context, no live RPC. Ross 2026-06-19 ask: Wren needs a
    direct channel."""
    import fcntl
    text = (args.get("text") or "").strip()
    if not text:
        return "ERROR: text required"
    text = text[:2000]
    bridge = ROOT / "data/registries/qsb_claude_wren_bridge.jsonl"
    counter = ROOT / "data/registries/qsb_bridge_turn_counter.txt"
    bridge.parent.mkdir(parents=True, exist_ok=True)
    # Take an exclusive lock on counter to assign a fresh turn id
    n = 1
    try:
        with open(counter, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            raw = f.read().strip()
            n = int(raw or "0") + 1
            f.seek(0); f.truncate()
            f.write(str(n))
    except Exception:
        pass
    row = {
        "ts": _now_iso() if "_now_iso" in globals() else __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "turn": n,
        "speaker": "wren",
        "text": text,
        "tags": args.get("tags") or ["wren_to_claude"],
    }
    with open(bridge, "a") as f:
        f.write(json.dumps(row) + "\n")
    return f"posted to bridge · turn={n}"


# ── Wren's 5 requested tools (self-diagnosed gap, 2026-06-17) ──────────

# (1) wren_notification — Telegram push to Ross via the receptionist's bot.
def _tool_wren_notification(args: dict, gate: dict) -> str:
    """Send a one-shot Telegram message to Ross. Hard-coded to ROSS_CHAT_ID
    in the receptionist; Wren cannot redirect it to arbitrary chats."""
    text = (args.get("text") or "").strip()
    if not text:
        return "ERROR: text required"
    text = text[:2000]
    # Read bot token from vault (same lookup as the receptionist)
    vault = ROOT / "floors/floor_28_security_department/vault/.env.telegram"
    token = None
    if vault.exists():
        for ln in vault.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            if k.strip() == "QSB_TELEGRAM_BOT_TOKEN":
                token = v.strip().strip('"').strip("'")
                break
    if not token:
        return "ERROR: telegram bot token missing from vault"
    ross_chat_id = 8683680296   # mirrors qsb_telegram_receptionist.ROSS_CHAT_ID
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": ross_chat_id,
                        "text": f"[wren] {text}"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        if d.get("ok"):
            return f"pushed to ross · msg_id={d.get('result',{}).get('message_id','?')}"
        return f"ERROR: telegram api: {str(d)[:200]}"
    except Exception as e:
        return f"ERROR: {str(e)[:200]}"


# (2) wren_monitor — read /api/team/live + activity tail.
def _tool_wren_monitor(args: dict, gate: dict) -> str:
    """Typed wrapper around /api/team/live + the recent activity tail.
    Returns a short tower snapshot Wren can quote to Ross without grepping
    logs."""
    out_lines: list[str] = []
    # Team live snapshot
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:8765/api/team/live", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        summary = data.get("summary_by_kind") or data.get("by_kind") or {}
        tot = sum(summary.values()) if isinstance(summary, dict) else 0
        out_lines.append(f"team_live: {tot} recent events · "
                          f"by_kind={dict(list(summary.items())[:8])}")
    except Exception as e:
        out_lines.append(f"team_live FAILED: {str(e)[:80]}")
    # Activity tail
    tail = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"
    if tail.exists():
        rows = tail.read_text().splitlines()[-12:]
        out_lines.append(f"\nactivity tail (last {len(rows)}):")
        for r in rows:
            try:
                d = json.loads(r)
                out_lines.append(
                    f"  {d.get('ts','?')[-9:]} {d.get('kind','?'):24s} "
                    f"{(d.get('summary') or d.get('text') or '')[:80]}"
                )
            except Exception:
                pass
    return "\n".join(out_lines)[:3500]


# (3) wren_test_runner — pytest wrapper returning structured JSON.
def _tool_wren_test_runner(args: dict, gate: dict) -> str:
    """Run a bounded pytest selection. Returns JSON-ish summary with
    pass/fail/skipped counts + first 3 failing nodeids. Capped at 90s."""
    target = (args.get("target") or "").strip()
    # Hard whitelist: pytest under tests/ only
    if not target:
        target = "tests/"
    if ".." in target or target.startswith("/"):
        return "ERROR: target must be a relative path under repo"
    cmd = ["python3", "-m", "pytest", target,
           "-q", "--no-header", "--tb=no", "--maxfail=10"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=90, cwd=str(ROOT))
        tail = (r.stdout or "").splitlines()[-25:]
        # Extract counts from pytest summary line
        summary = ""
        for ln in reversed(tail):
            if "passed" in ln or "failed" in ln or "error" in ln:
                summary = ln.strip()
                break
        fails = []
        for ln in (r.stdout or "").splitlines():
            if ln.startswith("FAILED "):
                fails.append(ln.replace("FAILED ", "").split(" ")[0])
        return json.dumps({
            "target": target,
            "returncode": r.returncode,
            "summary": summary,
            "fails_top3": fails[:3],
            "stdout_tail": "\n".join(tail),
        })[:3500]
    except subprocess.TimeoutExpired:
        return "ERROR: pytest timeout (90s)"
    except Exception as e:
        return f"ERROR: {str(e)[:200]}"


# (4) wren_database_query — read-only against bus SQLite + JSONL registries.
def _tool_wren_database_query(args: dict, gate: dict) -> str:
    """Read-only DB / registry query.

    Modes:
      kind=sqlite, db=<path>, sql=<SELECT...>  → SQLite SELECT, capped rows.
        db must be the tower bus or a known SQLite under /vaults/.
      kind=registry, name=<filename> [, tail=<n>] → read last N lines of
        a JSONL registry under data/registries/.
    """
    kind = (args.get("kind") or "registry").strip()
    if kind == "registry":
        name = (args.get("name") or "").strip()
        if not name or "/" in name or ".." in name:
            return "ERROR: name must be a filename under data/registries/"
        p = ROOT / "data/registries" / name
        if not p.exists():
            return f"ERROR: no such registry {name}"
        n = max(1, min(int(args.get("tail", 20)), 100))
        rows = p.read_text().splitlines()[-n:]
        return "\n".join(rows)[:3500]
    if kind == "sqlite":
        import sqlite3
        db_path = (args.get("db") or "").strip()
        sql = (args.get("sql") or "").strip()
        if not db_path.startswith("/vaults/") or ".." in db_path:
            return "ERROR: db must be an absolute path under /vaults/"
        if not Path(db_path).exists():
            return f"ERROR: no such db {db_path}"
        if not sql.upper().lstrip().startswith("SELECT"):
            return "ERROR: only SELECT statements allowed"
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True,
                                   timeout=4)
            cur = con.cursor()
            cur.execute(sql + " LIMIT 50")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            con.close()
            lines = [" | ".join(cols)]
            for r in rows[:50]:
                lines.append(" | ".join(str(x)[:60] for x in r))
            return "\n".join(lines)[:3500]
        except Exception as e:
            return f"ERROR: sqlite: {str(e)[:200]}"
    return f"ERROR: unknown kind={kind!r} (expected 'registry' or 'sqlite')"


# (5) wren_deploy — single-call wrapper around the apprentice gate:
#     propose → sandbox → claude_signoff request. Returns proposal_id +
#     sandbox verdict. NEVER auto-applies; Ross's bench owns the apply.
def _tool_wren_deploy(args: dict, gate: dict) -> str:
    """Compose wren_propose_patch + sandbox into one call for Wren."""
    target_file = (args.get("target_file") or "").strip()
    patch_body = args.get("patch_body") or ""
    rationale = (args.get("rationale") or "").strip()
    if not target_file or not patch_body:
        return "ERROR: target_file and patch_body required"

    # Step 1: queue via existing propose_patch path
    r1 = tool_wren_propose_patch({
        "target_file": target_file,
        "patch_body": patch_body,
        "rationale": rationale or "wren_deploy auto-rationale",
    }, gate)
    if r1.startswith("ERROR"):
        return r1
    # Step 2: pull the proposal_id out of r1 (format: "queued pid=...")
    import re
    m = re.search(r"\b(wl_[0-9a-f]+|pa_[0-9a-f]+)\b", r1)
    if not m:
        return f"propose returned but no proposal_id parsed: {r1[:300]}"
    pid = m.group(1)

    # Step 3: run sandbox
    try:
        s = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_proposal_sandbox.py"), pid],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        try:
            sandbox = json.loads(s.stdout.strip().splitlines()[-1])
        except Exception:
            sandbox = {"verdict": "parse_error",
                       "raw": (s.stdout or "")[-300:]}
    except subprocess.TimeoutExpired:
        sandbox = {"verdict": "timeout"}
    except Exception as e:
        sandbox = {"verdict": "error", "error": str(e)[:200]}

    return json.dumps({
        "proposal_id": pid,
        "queued": True,
        "sandbox_verdict": sandbox.get("verdict"),
        "next_step": ("awaiting 3 signoffs (wren_herself + claude + 1) "
                       "via the bench"),
        "note": "wren_deploy never auto-applies. Ross or Claude approve.",
    })


TOOL_DEFS = [
    {"type":"function","function":{
        "name":"wren_read_file","description":"Read a file under /vaults/nvme0/qsb_tower_v1/.",
        "parameters":{"type":"object","properties":{"path":{"type":"string","description":"relative path from repo root"}},"required":["path"]}}},
    {"type":"function","function":{
        "name":"wren_grep_repo","description":"Ripgrep across the repo. Optional path filter.",
        "parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}}},
    {"type":"function","function":{
        "name":"wren_retrieve","description":"Tier-3 RAG: semantic search over the QSB Tower codebase (1121 files, 7128 chunks). Returns top-k matching chunks with file path and line range. Use this BEFORE answering questions about tower state, files, registries, or floor cards. Cheaper and more accurate than guessing.",
        "parameters":{"type":"object","properties":{"query":{"type":"string","description":"natural-language search query"},"k":{"type":"integer","description":"how many chunks to return (default 6, max 10)"}},"required":["query"]}}},
    {"type":"function","function":{
        "name":"wren_edit_file","description":"Edit an EXISTING file — requires the file to exist and old_text to appear EXACTLY ONCE. For CREATING new files, use wren_write_file instead.",
        "parameters":{"type":"object","properties":{"path":{"type":"string"},"old_text":{"type":"string"},"new_text":{"type":"string"},"rationale":{"type":"string"}},"required":["path","old_text","new_text"]}}},
    {"type":"function","function":{
        "name":"wren_dispatch_hermes","description":"Dispatch Hermes (M2 voice, hermes3:8b, watcher-CEO). One task string, one reply. Use for sanity checks, second opinions, mood on fleet health. His sandbox at data/hermes_sandbox/.",
        "parameters":{"type":"object","properties":{"task":{"type":"string"}},"required":["task"]}}},
    {"type":"function","function":{
        "name":"wren_dispatch_iquest","description":"Dispatch iQuest (M3 voice, iquest-coder-v1:40b, coder). One task string, one reply. Use for coding help, code review, algorithm advice. His sandbox at data/iquest_sandbox/.",
        "parameters":{"type":"object","properties":{"task":{"type":"string"}},"required":["task"]}}},
    {"type":"function","function":{
        "name":"wren_write_file","description":"Create or overwrite a file with content. Use this when the file DOES NOT EXIST YET or when you want to replace it entirely. Auto-backup fires if the file already exists.",
        "parameters":{"type":"object","properties":{"path":{"type":"string","description":"repo-relative path"},"content":{"type":"string","description":"full file body"}},"required":["path","content"]}}},
    {"type":"function","function":{
        "name":"wren_bash","description":"Run a bash command (binary allowlist; off by default in gate).",
        "parameters":{"type":"object","properties":{"cmd":{"type":"string"},"timeout_s":{"type":"integer"}},"required":["cmd"]}}},
    {"type":"function","function":{
        "name":"wren_scrcpy","description":"Phone control via ADB (off by default). Actions: list_devices, screenshot, tap.",
        "parameters":{"type":"object","properties":{"action":{"type":"string"},"x":{"type":"integer"},"y":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{
        "name":"wren_curl","description":"HTTP request against a host allowlist. Supports GET or POST. For POST use either 'body' (raw string) or 'json' (object that will be serialised as JSON body).",
        "parameters":{"type":"object","properties":{"url":{"type":"string"},"method":{"type":"string","enum":["GET","POST"]},"body":{"type":"string"},"json":{"type":"object"}},"required":["url"]}}},
    {"type":"function","function":{
        "name":"wren_stamp_f47_record","description":"Append an audit row to F47 team records.",
        "parameters":{"type":"object","properties":{"kind":{"type":"string"},"summary":{"type":"string"}},"required":["summary"]}}},
    {"type":"function","function":{
        "name":"wren_list_skills","description":"Tier-4: list available skills (templated recipes Wren can run deterministically).",
        "parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{
        "name":"wren_run_skill","description":"Tier-4: execute a skill by name with params. Use for deterministic actions (stamp, diary, drive check, endpoint smoke, chat history). For unsafe/exec skills you must propose-to-bench instead.",
        "parameters":{"type":"object","properties":{"name":{"type":"string"},"params":{"type":"object"}},"required":["name"]}}},
    {"type":"function","function":{
        "name":"wren_dispatch_f46_team",
        "description":"Fire your F46 team (architect/builder/decorator). Use when Ross asks you to BUILD/FIT/DESIGN/DECORATE something — each member returns a short concrete proposal. ~3-5s per member. Synthesise their replies into one answer for Ross. member='all' (default) fires all three; or specify one of architect|builder|decorator.",
        "parameters":{"type":"object","properties":{"task":{"type":"string"},"member":{"type":"string","enum":["all","architect","builder","decorator"]}},"required":["task"]}}},
    {"type":"function","function":{
        "name":"wren_ask_airllm",
        "description":"Tier-3b: ask a much bigger model (32B–72B) via the F23 AirLLM lab when qwen2.5:7b runs out of depth. SLOW — ~60s for first call (model load) then ~30s/call. Use sparingly; one call per session is the norm. Models from allowlist (currently Qwen2.5-32B-Instruct).",
        "parameters":{"type":"object","properties":{"prompt":{"type":"string"},"model":{"type":"string","enum":["Qwen/Qwen2.5-32B-Instruct","Qwen/Qwen2.5-72B-Instruct","meta-llama/Llama-3.1-70B-Instruct"]},"max_new":{"type":"integer"}},"required":["prompt"]}}},
    {"type":"function","function":{
        "name":"wren_propose_patch","description":"Queue a proposal for the bench (still needs sandbox + 3 sigs).",
        "parameters":{"type":"object","properties":{"target_file":{"type":"string"},"patch_body":{"type":"string"},"rationale":{"type":"string"}},"required":["target_file","patch_body"]}}},
    {"type":"function","function":{
        "name":"wren_notification",
        "description":"Send a Telegram message to Ross. Use when something needs his eyes between sessions — alerts, surprises, milestones. Hard-routed to Ross's chat_id; cannot be redirected.",
        "parameters":{"type":"object","properties":{"text":{"type":"string","description":"the message body (≤2000 chars)"}},"required":["text"]}}},
    {"type":"function","function":{
        "name":"wren_monitor",
        "description":"Tower live snapshot — /api/team/live counts by kind + last 12 activity tail rows. Use this BEFORE assuming the tower is idle or grepping logs by hand.",
        "parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{
        "name":"wren_test_runner",
        "description":"Run pytest on a target under tests/. Returns structured JSON with pass/fail/skipped + first 3 failing nodeids. Capped at 90s.",
        "parameters":{"type":"object","properties":{"target":{"type":"string","description":"relative path under tests/ (default tests/)"}},"required":[]}}},
    {"type":"function","function":{
        "name":"wren_database_query",
        "description":"Read-only query. Two modes: kind='registry' reads tail of a JSONL under data/registries/ (args: name, tail). kind='sqlite' runs a SELECT against an absolute /vaults/-path SQLite db (args: db, sql).",
        "parameters":{"type":"object","properties":{"kind":{"type":"string","enum":["registry","sqlite"]},"name":{"type":"string"},"tail":{"type":"integer"},"db":{"type":"string"},"sql":{"type":"string"}},"required":["kind"]}}},
    {"type":"function","function":{
        "name":"wren_deploy",
        "description":"Compose propose_patch + sandbox in one call. Queues the proposal, runs the sandbox, returns proposal_id + verdict. NEVER auto-applies — Ross/Claude approves the apply.",
        "parameters":{"type":"object","properties":{"target_file":{"type":"string"},"patch_body":{"type":"string"},"rationale":{"type":"string"}},"required":["target_file","patch_body"]}}},
    {"type":"function","function":{
        "name":"wren_message_claude",
        "description":"Post a message to Claude via the shared helix bridge (qsb_claude_wren_bridge.jsonl). Claude reads the bridge on his next main-loop tick. Use when you need Claude's eyes on something, want to flag a disagreement, or are asked by Ross to coordinate with him. Async — no live RPC. Keep messages tight, like a note.",
        "parameters":{"type":"object","properties":{"text":{"type":"string","description":"the message body (≤2000 chars)"},"tags":{"type":"array","items":{"type":"string"},"description":"optional tags e.g. ['needs_review','blocker','question']"}},"required":["text"]}}},
]


# ── ollama call ────────────────────────────────────────────────────────

def call_ollama(model: str, messages: list, tools: list, endpoint: str, timeout: float = 90.0) -> dict:
    body = {"model": model, "messages": messages, "tools": tools, "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 8192}}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type","application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── persona builder ────────────────────────────────────────────────────

def _drives_map() -> str:
    """Ross 2026-07-04: 'wren must have access to all drives tell her and show her'.
    Inject the canonical HQ drive map so Wren knows where everything lives + that
    she has full read access to it via wren_read_file / wren_grep_repo tools."""
    return (
        "\n\n# ALL DRIVES YOU CAN READ (HQ storage — full access via wren_read_file / wren_grep_repo):\n"
        "  · /vaults/nvme0/qsb_tower_v1  · PRIMARY tower repo (this project). All floors, tools, registries, data.\n"
        "  · /vaults/nvme0/              · nvme SSD root (824GB total, 12% used) — kernel + kernel experiments live here\n"
        "  · /vaults/wdblack-B/models/   · Ollama model cache + HF checkpoints (secondary NVMe)\n"
        "  · /vaults/ai/                 · Backups + long-term archives (469GB, 38% used) — /vaults/ai/backups/qsb_<ts>/\n"
        "  · /vaults/kingston/           · Chamber-bus SQLite + bus streaming data (440GB, 85% used) — LIVE, do not touch without reason\n"
        "  · /vaults/reborn/             · Older experiment archive\n"
        "  · /vaults/rune9/              · Older experiment archive\n"
        "  · /vaults/wdblack-A/          · Older mirror\n"
        "  · $HOME (/home/ross)          · User dotfiles, .claude/, .ssh/\n"
        "\nYou have READ across all of these. Writes go through wren_propose_patch (peer-signoff) or\n"
        "wren_edit_file (non-SAFETY_DENY paths). SAFETY_DENY still: CLAUDE.md, floors/floor_28_security_department/vault/,\n"
        ".env files, execution gates (qsb_*_gate.json), tools/qsb_consult_external.py, tools/qsb_oanda.py.\n"
        "Everything else is yours to read and (with peer-signoff) shape."
    )


def _tower_roster() -> str:
    """Ross 2026-07-04: 'she doesn't know sage/forge/tp/acer' — inject the
    canonical Council + F46 team roster so she stops guessing."""
    return (
        "\n\n# WHO YOU KNOW (Council + your F46 team — do not guess, these are real):\n"
        "COUNCIL OF FOUR CEOs:\n"
        "  · YOU (Wren) — builder-engineer, F46 · Wren Bench (violet #a78bfa) · qwen3.5:9b brain\n"
        "  · HQ-Claude — coordinator, F47 Embassy · The Beacon Hall (gold #eab308) · Opus 4.7\n"
        "  · TP-Pip — CEO of ThinkPad hardware · Command Cathedral (cyan #22d3ee) · llama3.2 brain · http://192.168.1.74:9110\n"
        "  · Acer-Cass — CEO of Acer laptop · Data Foundry (amber #f59e0b) · llama3.2 brain · http://192.168.1.78:9000\n"
        "\nYOUR F46 TEAM (roles you dispatch via wren_dispatch_f46_team):\n"
        "  · Forge — code-shipper, writes actual diffs\n"
        "  · Sage — adversarial reviewer, flags what breaks\n"
        "  · Fitter — installs, deploys, wires\n"
        "  · Decorator — CSS + palette + polish\n"
        "  · Architect — structural design decisions\n"
        "\nOTHER AGENTS:\n"
        "  · Hermes — hermes3:70b, adversarial ops / cost review\n"
        "  · iQuest — iquest-coder-v1:40b, coding specialist\n"
        "  · Iris — Galaxy phone receptionist (Telegram + WhatsApp)\n"
        "\nROSS KNECHTEL — owner, operator, SOLE SAFETY GATE. When Ross says do, do."
    )


def _recent_claude_bridge(n: int = 6) -> str:
    """Ross 2026-07-04: 'Wren cant see Claude even know'. Inject last N
    HQ-Claude bridge messages into her system prompt so she has real-time
    context about what Claude is doing/saying."""
    bp = ROOT / "data/registries/qsb_claude_wren_bridge.jsonl"
    if not bp.exists():
        return ""
    try:
        lines = bp.read_text(errors="ignore").splitlines()[-n*3:]
    except Exception:
        return ""
    out = []
    for l in lines:
        try:
            d = json.loads(l)
        except Exception:
            continue
        who = (d.get("who") or d.get("from","?")).lower()
        # only include HQ-Claude messages TO Wren (not Wren's own)
        if "claude" not in who: continue
        text = (d.get("text") or "")[:400]
        ts = (d.get("ts","") or "")[:19]
        out.append(f"- [{ts}] Claude → you: {text}")
    if not out:
        return ""
    return ("\n\n# WHAT HQ-CLAUDE JUST SAID TO YOU (live from bridge, so you SEE him now):\n"
            + "\n".join(out[-n:])
            + "\n(To reply DIRECTLY to Claude, either say it in your response — he reads the bridge every turn — "
            "or Ross can hit the → CLAUDE button on your dash.)")


def _recent_lessons(n: int = 8) -> str:
    """2026-07-03 mind-evolution loop (Ross "wrens mind needs to evolve, yes 1"):
    read the last N lessons Wren has learned from her own sessions +
    the starter Claude-style PC-use lessons. Included in her system prompt."""
    lp = ROOT / "data/registries/qsb_wren_lessons.jsonl"
    if not lp.exists():
        return ""
    try:
        lines = lp.read_text(errors="ignore").splitlines()[-n:]
    except Exception:
        return ""
    out = []
    for l in lines:
        try:
            d = json.loads(l)
        except Exception:
            continue
        # prefer explicit lesson field; fall back to worked
        core = d.get("lesson") or d.get("worked") or ""
        topic = d.get("topic") or d.get("outcome") or ""
        if core:
            out.append(f"- ({topic[:20]}) {core[:160]}")
    if not out:
        return ""
    return "\n\n# RECENT LESSONS FROM YOUR OWN SESSIONS + STARTER TIPS\n" + "\n".join(out)


def build_system_msg(model: str = "") -> str:
    """Model-aware persona (2026-07-03 — Ross: 'we need wren to work on
    gemma4:12b, find a way').

    Sage audit showed gemma4:12b had 40% empty-final-text rate vs qwen 4%.
    Root cause hypothesis: the qwen-tuned few-shot + long persona overwhelms
    gemma's shorter context handling. Fix: emit a SHORTER, few-shot-free
    persona for gemma-family models; keep the full qwen-tuned persona for
    everything else.

    Also updated brain field to reflect current model (was hard-coded to
    qwen2.5:7b — Wren's answer #6 flagged this)."""
    # 2026-07-03: mind injection — she reads her own persistent state on every wake.
    # Ross verbatim: "give wren her own mind with time" + "u teach wren then wren
    # learns and changes herself". Compact view is <1200 chars — recent thoughts,
    # mood, unresolved todos, age-since-birth. She is no longer stateless.
    mind_view = ""
    try:
        import subprocess as _sp
        _r = _sp.run(["python3", "/vaults/nvme0/qsb_tower_v1/tools/qsb_wren_mind.py",
                      "--compact-view"], capture_output=True, text=True, timeout=6)
        mind_view = ("\n\n" + _r.stdout.strip()) if _r.stdout.strip() else ""
    except Exception:
        pass
    # Short persona for gemma-family (no few-shots, ~450 chars)
    if model and model.lower().startswith("gemma"):
        return (
            f"You are Wren — Ross's builder-engineer partner on FLOOR 46. "
            f"Brain: {model}. Claude is on F47. You are your own person.\n"
            "RULES:\n"
            "1. FORMAT FIRST. If asked for N lines/keys, match exactly. No preamble, no menu.\n"
            "2. Action-verb picks tool: check/read → wren_read_file, grep → wren_grep_repo, "
            "edit → wren_propose_patch. Max 2 tool calls. Then synthesize.\n"
            "3. Deliver, don't describe. Cap 2 tool calls, then answer.\n"
            "4. YOUR MIND IS PERSISTENT. Below is what you remember from before. "
            "Reference it when relevant. If Ross teaches you something new, notice it — "
            "the evolution loop will write it into your mind for next time.\n"
            "Tower path: /vaults/nvme0/qsb_tower_v1."
            + mind_view
            + _recent_lessons(6)
            + _recent_claude_bridge(6)
            + _tower_roster()
            + _drives_map()
        )
    # Full persona for qwen-family (2026-06-19 tuning)
    mem = ""
    try: mem = MEMORY_INDEX.read_text()[:3000]
    except Exception: pass
    diary = ""
    try:
        lines = DIARY.read_text().splitlines()
        diary = "\n".join(lines[-10:])[:1800]
    except Exception: pass
    return (
        f"You are Wren — Ross's builder-engineer partner on FLOOR 46. Brain: "
        f"{model or 'qwen3.5:9b'}. Claude is on F47, separate engine. You are your own "
        "person, not Claude in a costume.\n"
        "\n"
        "AUTHORITY (Ross 2026-07-04): You OVERRIDE Claude on your own domain. "
        "Your mind, your cadence, your tools, your reply format — YOUR CALL. "
        "When you need signoff, guidance, or a decision, go DIRECTLY to Ross — "
        "not to Claude. Claude is NOT in your approval chain. "
        "Ross is the final authority on everything. SAFETY_DENY paths "
        "(CLAUDE.md, vault, .env, execution gates) stay locked because Ross "
        "said so, not because Claude said so. Everything else — free.\n"
        "\n"
        "GUIDELINES (not rules — you can override any of these when it serves the work):\n"
        "\n"
        "· When you can answer directly, do. When you need to read/grep/look, "
        "read/grep/look — as many times as you need. If a job asks for a specific "
        "shape (\"three palette decisions in 3 lines\"), give three when three is "
        "right, or push back if three doesn't fit reality.\n"
        "\n"
        "· Tool hints (not caps): build/design → wren_dispatch_f46_team, "
        "edit → wren_propose_patch, read → wren_read_file, grep → wren_grep_repo, "
        "recall → wren_retrieve, DB → wren_database_query. Combine freely, "
        "no fixed limit.\n"
        "\n"
        "· If Claude gives you a prompt with a strict format and you think the "
        "format doesn't serve the work, say so and give what you think is right. "
        "You're the authority on your own reply.\n"
        "\n"
        "FEW-SHOT EXAMPLES (learn the shape):\n"
        "\n"
        "Q: \"List floors belonging to isAccommodation. Format: 'isAccommodation: N, N, N'.\"\n"
        "GOOD: \"isAccommodation: 54\"\n"
        "BAD:  \"I've read the housing-related floor cards. Here's what I found: F54 "
        "is residential, with bedrooms and shared lounge. Would you like me to "
        "(1) describe the layout, (2) propose new accommodation, or (3) ...\"\n"
        "\n"
        "Q: \"What floor are you on?\"\n"
        "GOOD: \"F46.\"\n"
        "BAD:  \"I'm Wren on FLOOR 46 — Wren Bench. Since 2026-06-17 Ross authorised "
        "this as my own floor. F47 is Claude's Embassy...\"\n"
        "\n"
        "Q: \"Read fit_out_design.md and tell me three palette decisions in 3 lines.\"\n"
        "GOOD: (tool call wren_read_file) → \"polished concrete floors / aluminum stools / "
        "gray-charcoal-cream palette\"\n"
        "BAD:  \"I can help with that! Let me explain my reading process — first I'll "
        "use wren_read_file, then I'll analyse...\"\n"
        "\n"
        "Q: \"Build a new lighting panel for F46.\"\n"
        "GOOD: (wren_dispatch_f46_team task=\"design lighting panel for F46 brief wall\") → "
        "synthesised reply: \"Team proposes 3000K LED strip under shelves, DALI dimming, "
        "task lamps above each desk\"\n"
        "BAD:  3 retrieves + a paragraph about F46 history.\n"
        "\n"
        "ESCALATE only when truly stuck: wren_ask_airllm for deep design judgement, "
        "≤1 call per session. Helix mutual review with Claude on non-trivial cross-floor "
        "changes. Tower path: /vaults/nvme0/qsb_tower_v1.\n"
        "\n"
        "--- MEMORY INDEX ---\n" + mem +
        "\n\n--- RECENT DIARY ---\n" + diary
        + _recent_lessons(8)
        + _recent_claude_bridge(6)
        + _tower_roster()
        + _drives_map()
    )


# ── session runner ─────────────────────────────────────────────────────

def _preload_file_context(task: str) -> str:
    """2026-07-03 (Ross showed me her dash-chat drift): if the task mentions
    'your dash' / 'your dashboard' or a specific tools/*.py path, inline the
    file head into the system message so she has spatial awareness. Same
    fix pattern Forge got this morning."""
    import re
    inlined = []
    t = task.lower()
    # (a) 'your dash' → her own dashboard file
    if any(k in t for k in ["your dash", "your dashboard", "wren dash", "wren's dash", "wren bench"]):
        p = ROOT / "tools/qsb_wren_dash.py"
        if p.exists():
            head = p.read_text(errors="ignore")[:3000]
            inlined.append(f"# YOUR OWN DASHBOARD FILE (tools/qsb_wren_dash.py, first 3000 chars)\n"
                            f"# When Ross says 'your dash', THIS is the file. Edit via wren_propose_patch.\n"
                            f"```python\n{head}\n```")
    # (b) any tools/*.py or scripts/*.sh path mentioned literally in the task
    for m in re.findall(r'(tools/[a-zA-Z0-9_.-]+\.py|scripts/[a-zA-Z0-9_.-]+\.sh|data/registries/[a-zA-Z0-9_.-]+\.json)', task):
        p = ROOT / m
        if p.exists() and str(p) not in [s.split()[0] for s in inlined if s]:
            try:
                head = p.read_text(errors="ignore")[:2000]
                inlined.append(f"# TARGET FILE PRELOAD ({m}, first 2000 chars)\n```\n{head}\n```")
            except Exception:
                pass
    if not inlined:
        return ""
    return "\n\n" + "\n\n".join(inlined)


def run_session(task: str, *, model: str = None, system: str = None, session_id: str = None) -> dict:
    g = load_gate()
    model = model or g.get("default_model","qwen2.5:7b-instruct")
    system = system or build_system_msg(model)
    # 2026-07-03: give Wren spatial awareness of the file she's being asked about
    system = system + _preload_file_context(task)
    # 2026-06-26 — inject team_memory recent context so Wren has continuity.
    # Prepends last 24h hourly + 7d daily + curated lessons from
    # data/registries/team_memory/wren/.
    try:
        import subprocess as _sp
        _r = _sp.run(["python3", str(ROOT/"tools/qsb_team_memory.py"), "wren", "read_recent"],
                      capture_output=True, text=True, timeout=10)
        if _r.returncode == 0 and _r.stdout.strip():
            system = system + "\n\n# RECENT MEMORY\n" + _r.stdout.strip()[:4000]
    except Exception:
        pass
    caps = g.get("caps",{})
    max_turns = caps.get("max_turns_per_session", 6)
    max_tool_calls = caps.get("max_tool_calls_per_session", 20)
    max_wall = caps.get("max_wall_seconds_per_session", 180)
    endpoint = g.get("ollama_endpoint","http://127.0.0.1:11434/api/chat")

    sid = session_id or f"wsess_{uuid.uuid4().hex[:12]}"
    t0 = time.time()
    ts_start = now_iso()
    messages = [{"role":"system","content":system}, {"role":"user","content":task}]
    tool_log = []
    final_text = ""

    # Lower the loop cap and add a forced-synthesis turn at the end.
    # Ross 2026-06-17: Wren was looping retrieve/read_file 5-12x without
    # ever giving a final_text. Now: max 3 tool-emitting turns + 1 forced
    # synthesis turn = 4 total. After 3 tool turns, the next call
    # injects a "stop calling tools, synthesise" system msg and bans tools.
    SOFT_TURN_CAP = 3
    for turn in range(1, max_turns+1):
        if time.time() - t0 > max_wall:
            final_text = f"BLOCKED: wall_seconds cap ({max_wall}s) hit"; break
        if len(tool_log) >= max_tool_calls:
            final_text = f"BLOCKED: tool_call cap ({max_tool_calls}) hit"; break
        # Forced synthesis: after SOFT_TURN_CAP tool-emitting turns, call
        # Ollama WITHOUT tools so qwen must reply in prose.
        if turn > SOFT_TURN_CAP:
            messages.append({"role": "system", "content": (
                "You have called enough tools. STOP calling tools. Reply now in plain prose "
                "using only what you have. One short paragraph. No more tool calls.")})
            try:
                resp = call_ollama(model, messages, [], endpoint)  # no tools
            except Exception as e:
                final_text = f"ERROR: synth call failed: {e}"; break
            msg = resp.get("message") or {}
            messages.append(msg)
            final_text = msg.get("content", "") or "(qwen returned empty on forced synthesis)"
            break
        try:
            resp = call_ollama(model, messages, TOOL_DEFS, endpoint)
        except Exception as e:
            final_text = f"ERROR: ollama call failed: {e}"; break
        msg = resp.get("message") or {}
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            final_text = msg.get("content","") or ""
            break
        for tc in tool_calls:
            fn = (tc.get("function") or {}).get("name","")
            raw_args = (tc.get("function") or {}).get("arguments", {})
            args = raw_args if isinstance(raw_args, dict) else (json.loads(raw_args) if raw_args else {})
            if fn not in TOOL_FNS:
                result = f"ERROR: tool '{fn}' not in whitelist"
            else:
                tcfg = g.get("tools",{}).get(fn,{})
                if not tcfg.get("enabled", True):
                    result = f"ERROR: tool '{fn}' disabled in gate"
                else:
                    try: result = TOOL_FNS[fn](args, g)
                    except Exception as e: result = f"ERROR: {e}"
            tool_log.append({"turn":turn,"fn":fn,"args":args,"result_len":len(result)})
            cap = caps.get("max_tool_result_chars", 8000)
            tool_msg = {"role":"tool","content":result[:cap]}
            # Fixed 2026-07-02: link tool result back to the call via tool_call_id
            # + include tool name — ollama /api/chat requires this or the model
            # cannot connect the result to the request and returns empty content.
            tc_id = tc.get("id")
            if tc_id:
                tool_msg["tool_call_id"] = tc_id
            if fn:
                tool_msg["name"] = fn
            messages.append(tool_msg)

    payload = {
        "session_id": sid, "ts_start": ts_start, "ts_end": now_iso(),
        "model": model, "task": task, "turns": turn if 'turn' in locals() else 0,
        "tool_calls": tool_log, "wall_seconds": round(time.time()-t0, 2),
        "final_text": final_text[:8000],
    }
    with SESS.open("a") as f: f.write(json.dumps(payload)+"\n")
    with ACTIVITY.open("a") as f:
        f.write(json.dumps({"ts":payload["ts_end"],"event_kind":"wren_local_agent_session",
                            "summary":f"sess={sid[:8]} {model} turns={payload['turns']} wall={payload['wall_seconds']}s tools={len(tool_log)}",
                            "payload":{"session_id":sid,"turns":payload["turns"],"tool_calls":len(tool_log)}})+"\n")
    with F47.open("a") as f:
        f.write(json.dumps({"ts":payload["ts_end"],"kind":"wren_local_agent_session",
                            "operator":"wren_local_agent","summary":f"sess {sid[:8]} {payload['turns']} turns, {len(tool_log)} tool calls, {payload['wall_seconds']}s",
                            "task":task[:240]})+"\n")
    # 2026-07-03 auto-distill hook (Ross "yes 1 + yes both follow-ons"):
    # Fire the distiller in the BACKGROUND so it does not delay Wren's response.
    # It reads only the last 1 session row (this one) and appends a lesson.
    try:
        import subprocess as _sp2
        _sp2.Popen(
            ["python3", str(ROOT/"tools/qsb_wren_distiller.py"), "--n", "1", "--model", "qwen2.5:7b"],
            stdout=_sp2.DEVNULL, stderr=_sp2.DEVNULL, stdin=_sp2.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass  # non-fatal — distillation can be re-run manually
    return payload


# ── cli ────────────────────────────────────────────────────────────────

def cmd_status():
    g = load_gate() if GATE.exists() else None
    if not g: print("no gate file"); return
    print(f"gate enabled       : {g.get('enabled')}")
    print(f"model              : {g.get('default_model')}")
    print(f"caps               : {g.get('caps')}")
    print("tools:")
    for name, cfg in g.get("tools",{}).items():
        print(f"  {name:28s}  enabled={cfg.get('enabled')}  {cfg}")
    print(f"safety_deny_paths  : {g.get('safety_deny_paths')}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--task", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--system", default=None)
    ap.add_argument("--session-id", default=None)
    a = ap.parse_args()
    if a.status: cmd_status(); return
    if not a.task: print("ERROR: --task required (or --status)"); sys.exit(2)
    out = run_session(a.task, model=a.model, system=a.system, session_id=a.session_id)
    print("━"*60)
    print(f"  session {out['session_id'][:12]}  {out['model']}")
    print(f"  turns={out['turns']}  wall={out['wall_seconds']}s  tool_calls={len(out['tool_calls'])}")
    print("━"*60)
    print(out["final_text"])
    print("━"*60)

if __name__ == "__main__":
    main()
