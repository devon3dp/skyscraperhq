#!/usr/bin/env python3
"""qsb_local_agent.py — dispatch a local Ollama-backed agent for a typed job.

Ross 2026-06-19: "how can we make our local agents" — answer is one
typed-role dispatcher that picks the right local model + persona for the
job type. All runs cost $0 (local), stamp F47, and write to a local-agent
ledger so we can review what they did.

Usage:
  python3 tools/qsb_local_agent.py --role researcher --task "Audit qsb_f42_*"
  python3 tools/qsb_local_agent.py --role coder --task "Sketch a faster ..."
  python3 tools/qsb_local_agent.py --role auditor --task "Look at recent ..."

Roles → model + persona:
  researcher  → hermes3:8b — reads registries, summarises, cites sources
  coder       → qwen2.5-coder:7b-instruct — proposes code (queued via bench)
  auditor     → hermes3:8b — sweeps logs + registries for anomalies
  strategist  → hermes3:8b — proposes new trader strategies from board data
"""

from __future__ import annotations
import argparse, datetime, json, subprocess, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
LEDGER = ROOT / "data/registries/qsb_local_agent_runs.jsonl"

ROLES = {
    "researcher": {
        "model": "hermes3:8b",
        "tools": ["qsb_read_registry", "qsb_read_floor_card", "qsb_grep_repo"],
        "persona": (
            "You are a research worker on the QSB Tower. Answer the task "
            "directly. If — and only if — you need primary-source data from "
            "the repo to answer accurately, you may call qsb_grep_repo "
            "(pattern), qsb_read_registry (path), or qsb_read_floor_card "
            "(floor). For self-contained questions, just answer. Output what "
            "the task asks for — if it asks for JSON, return JSON only."
        ),
    },
    "coder": {
        "model": "qwen2.5-coder:7b-instruct",
        "tools": ["qsb_read_registry", "qsb_grep_repo",
                   "qsb_propose_patch", "qsb_stamp_f47_record"],
        "persona": (
            "You are a code worker on the QSB Tower. If the task asks for a "
            "patch: read the target file via qsb_read_registry or "
            "qsb_grep_repo, then call qsb_propose_patch with target_file + "
            "the FULL replacement file content in patch_body (empty patches "
            "are rejected). If the task asks for a code sketch or review "
            "WITHOUT a patch, just return code/text directly — no tool needed."
        ),
    },
    "auditor": {
        "model": "hermes3:8b",
        "tools": ["qsb_read_registry", "qsb_read_floor_card",
                   "qsb_grep_repo", "qsb_stamp_f47_record"],
        "persona": (
            "You are an audit worker on the QSB Tower. Sweep the registry "
            "or log indicated in the task, flag any anomaly (silent error, "
            "stuck counter, mismatched schema, gate left open, runaway "
            "growth). Output: a numbered list of findings, each with a "
            "file path + 1-line description. Stamp F47 at end."
        ),
    },
    "strategist": {
        "model": "hermes3:8b",
        # Strategist has NO tools — output is the answer itself.
        "tools": [],
        "persona": (
            "You are a strategy advisor on the QSB Tower. Output is always a "
            "single JSON object — never prose outside the JSON, never markdown "
            "fences. Choose from: momentum, mean_revert, scalp, random."
        ),
    },
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", required=True, choices=list(ROLES.keys()))
    p.add_argument("--task", required=True)
    p.add_argument("--session-id", default=None)
    p.add_argument("--model", default=None, help="override role default")
    a = p.parse_args()

    cfg = ROLES[a.role]
    model = a.model or cfg["model"]
    session_id = a.session_id or f"local_{a.role}_{int(datetime.datetime.now().timestamp())}"

    cmd = [
        "python3", str(ROOT / "tools/qsb_provider_agent.py"),
        "--provider", "ollama",
        "--model", model,
        "--system", cfg["persona"],
        "--task", a.task,
        "--session-id", session_id,
        "--allowed-tools", ",".join(cfg.get("tools") or []) or "none",
    ]
    t0 = datetime.datetime.now()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=300, cwd=str(ROOT))
        out = (r.stdout or "")[-2000:]
        rc = r.returncode
    except subprocess.TimeoutExpired:
        out = "ERROR: agent timeout 300s"
        rc = 1
    wall_s = (datetime.datetime.now() - t0).total_seconds()

    # Audit
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": now_iso(),
        "role": a.role, "model": model,
        "session_id": session_id,
        "task_head": a.task[:160],
        "wall_s": round(wall_s, 1),
        "rc": rc,
        "stdout_tail": out[-800:],
    }
    with open(LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")
    with open(F47, "a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "kind": "local_agent_run",
            "operator": f"local_agent.{a.role}",
            "summary": f"{a.role} @ {model} · {wall_s:.0f}s · rc={rc} · "
                        f"task: {a.task[:120]}",
        }) + "\n")
    print(out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
