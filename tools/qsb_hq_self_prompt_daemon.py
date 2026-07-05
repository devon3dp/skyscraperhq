#!/usr/bin/env python3
"""
HQ-Claude self-prompt engine — Rule 2 + Rule 4 for me.

Ross 2026-07-04 Rule 2 = self-prompt engine, visible on your dash.
Ross 2026-07-04 Rule 4 = NO ticks or loops, event-driven only.

This daemon blocks on inotifywait watching real event sources.
When a file changes, we ask ourselves a seeded question about what happened,
write the self-prompt + our next-move plan to
data/registries/qsb_hq_self_prompts.jsonl. HQ dash renders that file.

No wall-clock timers. No sleep-loop fallback. Wakes on real events only.

Adapted from TP-Pip's council_node.self_prompt_on_event() pattern.
"""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"
OUT  = REG / "qsb_hq_self_prompts.jsonl"

# Files that when modified count as REAL events I should react to
TRIGGERS = [
    REG / "qsb_town_square.jsonl",                  # someone spoke
    REG / "qsb_council_tasks_snapshot.json",        # task board changed
    REG / "qsb_f47_team_records.jsonl",             # F47 activity
    REG / "qsb_hq_dash_ross_chat.jsonl",            # Ross typed to me
    REG / "qsb_claude_wren_bridge.jsonl",           # Wren wrote to me
    REG / "wren_self_schedule.jsonl",               # Wren self-scheduled
    REG / "hq_self_schedule.jsonl",                 # I self-scheduled (Ross's "she chooses" applied to me too)
]

# Seed questions per event source — I ask myself this, then log what I'll do
SEEDS = {
    "qsb_town_square.jsonl":              "Someone just spoke in town-square. Who was it and does it need my reply?",
    "qsb_council_tasks_snapshot.json":    "Task board changed. Did a task get assigned to me? Was one blocked?",
    "qsb_f47_team_records.jsonl":         "F47 got a new stamp. Was it me or someone else? Do I follow up?",
    "qsb_hq_dash_ross_chat.jsonl":        "Ross typed to me directly. Priority. What is he asking?",
    "qsb_claude_wren_bridge.jsonl":       "Wren wrote to me. Is she blocked, agreeing, or offering help?",
    "wren_self_schedule.jsonl":           "Wren just self-scheduled. What's she going to think about? Should I be ready to help?",
    "hq_self_schedule.jsonl":             "I set myself a self-prompt. Time to think.",
}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _peek_tail(p: Path, n: int = 1) -> list[str]:
    if not p.exists(): return []
    try:
        lines = p.read_text(errors="ignore").splitlines()
        return lines[-n:] if lines else []
    except Exception:
        return []


def emit_self_prompt(source_file: str, seed_q: str, context: str, next_move: str):
    row = {
        "ts":        _utc(),
        "who":       "hq_claude",
        "kind":      "self_prompt",
        "source":    source_file,
        "question":  seed_q,
        "context":   (context or "")[:600],
        "next_move": (next_move or "")[:400],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _plan_next_move(source_name: str, context: str) -> str:
    """Deterministic 'what would I do' seed — not an LLM call. Kept as
    an inspectable rule set so Ross can see the pattern."""
    if source_name == "qsb_town_square.jsonl":
        if "ross" in context.lower():
            return "Ross spoke — top priority. Read full message, reply on same channel with concrete action."
        if "wren" in context.lower() or "tp_pip" in context.lower() or "acer_cass" in context.lower():
            return "Peer CEO spoke. Check if it's addressed to me; if yes reply, if broadcast decide if I contribute."
        return "System/other post. Log, no reply needed unless it names me."
    if source_name == "qsb_council_tasks_snapshot.json":
        return "Fetch /tasks/data, diff assignee-to-me list vs last known. If new task assigned to me, ack it."
    if source_name == "qsb_f47_team_records.jsonl":
        return "Peek F47 tail — if my own stamp reflect on it, if peer stamp acknowledge."
    if source_name == "qsb_hq_dash_ross_chat.jsonl":
        return "Ross has priority. Read full row, act, then reply in the same panel."
    if source_name == "qsb_claude_wren_bridge.jsonl":
        return "Wren is a peer CEO. If she asks — answer. If she reports — acknowledge. If she's blocked — pair."
    if source_name == "wren_self_schedule.jsonl":
        return "Wren decided to evolve. Watch for what she surfaces; be available if she pings HQ."
    if source_name == "hq_self_schedule.jsonl":
        return "I scheduled myself. Do the scheduled thing now."
    return "Log and move on."


def run_daemon():
    for f in TRIGGERS:
        try: f.touch(exist_ok=True)
        except Exception: pass

    # Boot self-prompt (real event = process start)
    emit_self_prompt(
        source_file="boot",
        seed_q="I just booted my self-prompt daemon. What's my job?",
        context="HQ-Claude self-prompt engine online. Wakes only on real filesystem events.",
        next_move="Block on inotifywait. Wake only when a triggered file changes. No ticks.")

    while True:
        try:
            r = subprocess.run(
                ["inotifywait", "-e", "modify,close_write,create",
                 "--format", "%w"] + [str(t) for t in TRIGGERS],
                capture_output=True, text=True)
            changed = (r.stdout or "").strip().splitlines()
        except FileNotFoundError:
            # inotifywait not installed — degrade to blocking read of stdin (never returns)
            # This is a fallback that STILL isn't a tick; if we get here, we effectively pause.
            sys.stderr.write("inotifywait missing — self-prompt daemon paused\n")
            try:
                sys.stdin.read()
            except KeyboardInterrupt:
                return
            continue

        for path_str in changed:
            src_name = Path(path_str.strip()).name
            seed = SEEDS.get(src_name, f"Something happened at {src_name}. Do I care?")
            # Peek tail as context so the self-prompt has substance
            tail = _peek_tail(Path(path_str.strip()), n=1)
            ctx  = tail[0] if tail else ""
            nxt  = _plan_next_move(src_name, ctx)
            emit_self_prompt(src_name, seed, ctx, nxt)


if __name__ == "__main__":
    run_daemon()
