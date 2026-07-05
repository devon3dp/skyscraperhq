#!/usr/bin/env python3
"""qsb_ollama_ask.py — generic Ollama adapter.

Reads shared brief + member private memory, calls the local model via Ollama,
writes response + appends decision/lesson if relevant. Never pretends success.

Usage:
  python3 qsb_ollama_ask.py --member wren --model qwen3.5:9b --task "..."
"""
from __future__ import annotations
import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SHARED = ROOT / "data/team_memory/shared"
OLLAMA = "http://127.0.0.1:11434/api/chat"


def utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_brief() -> str:
    f = SHARED / "shared_project_brief.md"
    return f.read_text() if f.exists() else "(no shared brief — run scripts/qsb_team_build_shared_project_brief.sh)"


def load_private(member: str) -> str:
    f = ROOT / f"data/team_memory/{member}/memory.md"
    return f.read_text() if f.exists() else "(no private memory yet)"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--member", required=True, help="claude/wren/hermes/iquest_coder")
    p.add_argument("--model", required=True, help="ollama model id")
    p.add_argument("--task", required=True)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--out", default="")
    args = p.parse_args()

    log_dir = ROOT / "data/logs/team"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else log_dir / f"{args.member}_latest_response.md"

    brief = load_brief()
    private = load_private(args.member)

    system = (
        f"You are {args.member} on the QSB Tower team. Read the shared brief and your "
        f"private memory below, then answer the task in <=200 words. Be concrete. "
        f"If you don't know, say so. End with one line:\n"
        f"NEXT: <one concrete action you propose>"
    )
    user_msg = (
        f"### SHARED PROJECT BRIEF\n{brief[:6000]}\n\n"
        f"### YOUR PRIVATE MEMORY ({args.member})\n{private[:2000]}\n\n"
        f"### TASK\n{args.task}\n"
    )

    # CLEAN-VOICE FIX: disable thinking-mode leak + hard stops so the model
    # answers once and stops (no <think> dump, no hallucinated next turn).
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 400,
            "stop": ["<|im_start|>", "<|im_end|>", "<|endoftext|>", "<think>"],
        },
    }

    t0 = time.time()
    err = None
    text = ""
    try:
        req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = json.loads(resp.read().decode())
        text = data.get("message", {}).get("content", "").strip()
        # belt-and-braces: drop any <think>...</think> block if the model still emits one
        import re as _re
        text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
        text = text.split("<|im_start|>")[0].split("<|endoftext|>")[0].strip()
    except Exception as e:
        err = str(e)

    elapsed = round(time.time() - t0, 1)
    success = bool(text and not err)

    # Write response file (honest — includes failures)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# {args.member} ({args.model}) — {utc_iso()}\n"
        f"- task: {args.task}\n"
        f"- wall_seconds: {elapsed}\n"
        f"- success: {success}\n"
        f"- error: {err or '(none)'}\n\n"
        f"## response\n{text or '(empty)'}\n"
    )
    out_path.write_text(body)

    # Append to last_model_calls.json
    reg = ROOT / "data/registries/qsb_team_last_model_calls.json"
    history: list = []
    if reg.exists():
        try: history = json.loads(reg.read_text())
        except Exception: history = []
    history.append({
        "ts": utc_iso(), "member": args.member, "model": args.model,
        "task_head": args.task[:120], "success": success,
        "wall_s": elapsed, "error": err, "out_path": str(out_path),
    })
    history = history[-50:]
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps(history, indent=2))

    # Append to member decisions.jsonl
    dec = ROOT / f"data/team_memory/{args.member}/decisions.jsonl"
    dec.parent.mkdir(parents=True, exist_ok=True)
    with dec.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(), "model": args.model, "task_head": args.task[:120],
            "success": success, "wall_s": elapsed, "out_path": str(out_path),
        }) + "\n")

    # Append summary to memory.md so the model sees its own history next call
    mem_md = ROOT / f"data/team_memory/{args.member}/memory.md"
    head = text.split("\n", 1)[0][:200] if text else "(no response)"
    next_line = ""
    for line in (text or "").splitlines():
        line = line.strip()
        if line.upper().startswith("NEXT:"):
            next_line = line[5:].strip()[:200]
            break
    if success and (head or next_line):
        with mem_md.open("a") as f:
            f.write(f"\n## {utc_iso()} — {args.member}\n"
                    f"- task: {args.task[:160]}\n"
                    f"- head: {head}\n"
                    f"- next: {next_line or '(none)'}\n"
                    f"- wall: {elapsed}s\n"
                    f"- log: {out_path}\n")

    # Stamp F47
    f47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
    with f47.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(), "kind": "team_model_call",
            "role": args.member, "model": args.model,
            "subject": args.task[:160], "success": success,
            "wall_s": elapsed, "out_path": str(out_path),
        }) + "\n")

    # RESPONSE-TO-STDOUT FIX: emit the actual response to stdout so callers/teammates
    # receive the LIVE words, not just metadata (the file-only output was read
    # back stale when a call ever failed -> the "always same text" bug).
    print("<<<WREN_RESPONSE>>>")
    print(text or "(empty)")
    print("<<<END_RESPONSE>>>")
    print(f"member={args.member} model={args.model} success={success} elapsed={elapsed}s out={out_path}")
    if err:
        print(f"ERROR: {err}")
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
