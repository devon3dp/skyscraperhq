#!/usr/bin/env python3
"""qsb_team_delegate_task.py — roundtable orchestrator.

Lead defines task → reviewers each weigh in (parallel) → consensus is computed
from real responses (no faking). Members that fail/timeout are marked honestly.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SHARED = ROOT / "data/team_memory/shared"

MEMBER_MODEL_DEFAULT = {
    "wren": "qwen3.5:9b",
    "hermes": "hermes3:8b",
    "iquest_coder": "iquest-coder-v1:40b-instruct",
}


def utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def dispatch(member: str, model: str, task: str, timeout: int) -> dict:
    log_path = ROOT / f"data/logs/team/{member}_latest_response.md"
    t0 = time.time()
    rc = subprocess.run(
        ["python3", "scripts/team_adapters/qsb_ollama_ask.py",
         "--member", member, "--model", model,
         "--task", task, "--timeout", str(timeout)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout + 30,
    )
    elapsed = round(time.time() - t0, 1)
    success = rc.returncode == 0
    content = log_path.read_text() if log_path.exists() else ""
    text = ""
    if "## response" in content:
        text = content.split("## response", 1)[1].strip()
    verdict = "needs_human_decision"
    text_lower = text.lower()
    if not success or not text or text == "(empty)":
        verdict = "model_unavailable"
    elif any(k in text_lower for k in ["approve", "approved", "agree", "yes", "ok"]):
        verdict = "approved"
    elif any(k in text_lower for k in ["concern", "but", "however", "caveat", "watch out"]):
        verdict = "approved_with_concerns"
    elif any(k in text_lower for k in ["block", "refuse", "no ", "wrong", "disagree"]):
        verdict = "blocked"
    return {
        "member": member, "model": model, "success": success,
        "wall_s": elapsed, "verdict": verdict,
        "head": text[:240] if text else "(no response)",
        "log": str(log_path),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--lead", default="claude")
    p.add_argument("--reviewers", default="wren,hermes,iquest_coder")
    p.add_argument("--output", default=str(ROOT/"data/logs/qsb_team_roundtable_latest.md"))
    p.add_argument("--timeout", type=int, default=240)
    args = p.parse_args()

    reviewers = [r.strip() for r in args.reviewers.split(",") if r.strip()]
    results = []
    with ThreadPoolExecutor(max_workers=min(4, len(reviewers))) as ex:
        futures = {ex.submit(dispatch, r, MEMBER_MODEL_DEFAULT.get(r, "qwen3.5:9b"),
                              args.task, args.timeout): r for r in reviewers}
        for f in as_completed(futures):
            results.append(f.result())

    available = sum(1 for r in results if r["verdict"] != "model_unavailable")
    approved = sum(1 for r in results if r["verdict"] in ("approved", "approved_with_concerns"))
    blocked  = sum(1 for r in results if r["verdict"] == "blocked")
    if available == 0:
        consensus = "model_unavailable"
    elif blocked > 0:
        consensus = "blocked"
    elif approved >= max(1, available // 2):
        consensus = "approved" if all(r["verdict"] == "approved" for r in results if r["verdict"] != "model_unavailable") else "approved_with_concerns"
    else:
        consensus = "needs_human_decision"

    out_md = Path(args.output)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(
        f"# Team Roundtable — {utc_iso()}\n\n"
        f"- task: {args.task}\n- lead: {args.lead}\n- reviewers: {', '.join(reviewers)}\n"
        f"- consensus: **{consensus}**\n\n"
        f"## reviewer verdicts\n" +
        "\n".join(f"- **{r['member']}** ({r['model']}) — {r['verdict']} ({r['wall_s']}s) — {r['head']}" for r in results)
        + "\n"
    )

    state_path = ROOT / "data/registries/qsb_team_consensus_latest.json"
    state_path.write_text(json.dumps({
        "ts": utc_iso(), "task": args.task, "lead": args.lead,
        "reviewers": reviewers, "consensus": consensus,
        "available": available, "approved": approved, "blocked": blocked,
        "results": results,
    }, indent=2))

    # F47 stamp
    f47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
    with f47.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(), "kind": "team_roundtable",
            "role": "claude", "subject": args.task[:160],
            "consensus": consensus, "approved": approved, "blocked": blocked,
            "available": available, "out_md": str(out_md),
        }) + "\n")

    print(f"consensus: {consensus}  available={available}/{len(reviewers)}  approved={approved}  blocked={blocked}")
    print(f"wrote {out_md}")
    print(f"wrote {state_path}")


if __name__ == "__main__":
    main()
