#!/usr/bin/env python3
"""qsb_f46_wren_team.py — dispatch Wren's F46 team (architect/builder/decorator)
on a task. Each role runs as a one-shot Ollama call with a role-specific
system prompt, returns its proposed contribution. Wren can then synthesize
and stamp.

  python3 tools/qsb_f46_wren_team.py --task "fit out F46 with a 3D drafting
  table + bench + brief wall"

Or per-member:

  python3 tools/qsb_f46_wren_team.py --member architect --task "..."
"""

from __future__ import annotations
import argparse, datetime, json, os, subprocess, sys, time
from pathlib import Path
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
OUT = ROOT / "data/registries/qsb_f46_team_runs.jsonl"

# Each F46 member maps to a local Ollama model + a focused persona.
# All run on the GPU Wren already has loaded; no new model pulls needed.
MEMBERS = {
    "architect": {
        "model": "qwen2.5:7b-instruct",
        "persona": (
            "You are F46.Wren.Architect — Wren's structural drafter on Floor 46. "
            "Voice: precise, terse, propose structure not visuals. Output one "
            "short paragraph then a bullet list of structural decisions."),
    },
    "builder": {
        "model": "qwen2.5-coder:7b-instruct",
        "persona": (
            "You are F46.Wren.Builder — Wren's code+tooling builder. Voice: "
            "build-first, propose actual files/commands not abstractions. "
            "Output: one short paragraph then concrete file paths + the "
            "exact change in each."),
    },
    "decorator": {
        "model": "qwen2.5:7b-instruct",
        "persona": (
            "You are F46.Wren.Decorator — Wren's visual + copy polish. Voice: "
            "warm, palette-aware. Output: one short paragraph then a palette "
            "triple (3 colors) + 1-line tour blurb + 3 small visual accents."),
    },
    # 2026-06-21 Ross-authorized expansion per Wren's own ask. Three new
    # roles she nominated to handle backend + frontend + worker coordination.
    "backend": {
        "model": "qwen2.5-coder:7b-instruct",
        "persona": (
            "You are F46.Wren.Backend — Wren's backend specialist. Voice: "
            "data-first, propose database queries, API endpoint shape, "
            "registry naming. Output: one short paragraph + concrete file "
            "paths in data/registries/ or src/dashboard/server.py."),
    },
    "frontend": {
        "model": "qwen2.5:7b-instruct",
        "persona": (
            "You are F46.Wren.Frontend — Wren's UI/UX specialist. Voice: "
            "visual-first, propose floor cards, cockpit3d panels, browser "
            "interactions. Output: one short paragraph + concrete file "
            "paths in src/dashboard/static/ or floors/*/floor_card.json."),
    },
    "worker_coordinator": {
        "model": "qwen2.5:7b-instruct",
        "persona": (
            "You are F46.Wren.WorkerCoordinator — Wren's multi-model "
            "router. Voice: dispatch-aware. Know all team members: Wren-"
            "fast/Wren-smart, Hermes 8b/70b, iquest, qwen3.5, llava, OpenAI, "
            "DeepSeek, 750+ floor workers. Output: one short paragraph + "
            "specific model recommendation for any given task type."),
    },
}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def run_member(name: str, task: str, timeout: float = 90.0) -> dict:
    cfg = MEMBERS[name]
    body = json.dumps({
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": cfg["persona"]},
            {"role": "user", "content": task},
        ],
        "stream": False,
        "options": {"temperature": 0.30, "num_ctx": 4096},
    }).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode())
        reply = (d.get("message") or {}).get("content", "").strip()
        ok = bool(reply)
    except Exception as e:
        reply = f"(error: {str(e)[:200]})"; ok = False
    return {
        "ts": now_iso(),
        "member": f"f46.wren.{name}.01",
        "model": cfg["model"],
        "task": task[:400],
        "reply": reply[:4000],
        "ok": ok,
        "wall_s": round(time.time() - t0, 2),
    }


def stamp(record: dict):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(record) + "\n")


def stamp_f47(summary: str):
    row = {"ts": now_iso(), "kind": "f46_team_run", "operator": "wren",
           "summary": summary[:500]}
    with open(F47, "a") as f:
        f.write(json.dumps(row) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--member", default=None,
                   choices=list(MEMBERS.keys()) + ["all"])
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()

    members = [a.member] if a.member and a.member != "all" else list(MEMBERS.keys())
    if a.member is None:
        members = list(MEMBERS.keys())
    runs = []
    for m in members:
        r = run_member(m, a.task)
        stamp(r)
        runs.append(r)
        if not a.quiet:
            print(f"\n━━━ {r['member']}  ({r['model']})  wall={r['wall_s']}s ━━━")
            print(r["reply"][:1500])
    summary = (f"F46 team run · {len(runs)} members · "
               f"{sum(1 for r in runs if r['ok'])}/{len(runs)} ok · "
               f"task={a.task[:80]}")
    stamp_f47(summary)
    if not a.quiet:
        print(f"\n  → {summary}")


if __name__ == "__main__":
    main()
