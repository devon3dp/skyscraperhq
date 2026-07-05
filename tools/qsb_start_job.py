#!/usr/bin/env python3
"""qsb_start_job.py — START gate: consult an advisor + dispatch a teammate
+ stamp the job_started F47 row, all in one call. Job is not "started"
until this writes a row with BOTH advisor_consulted AND team_dispatched fields.

Per Ross 2026-06-16 directive: every job needs structural team involvement
because "remembering to delegate" hasn't worked across multiple sessions.

  python3 tools/qsb_start_job.py "<job-title>" \\
      --question "<one-line advisor question>" \\
      [--advisor wren|auger|deepseek|openai]   default: wren
      [--teammate forge|pip|mira|bram|cass]    default: forge
      [--task "<one-line teammate task>"]      default: derived from title

Output (printed to stdout): JSON with {job_id, advisor_reply_first_line,
team_dispatched, started_ts}. The job_id should be passed to qsb_end_job.py.
"""

from __future__ import annotations
import argparse, datetime, json, os, subprocess, sys, hashlib
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _stamp(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def consult_wren(question: str, timeout: int = 90) -> str:
    """POST to /api/f47_chat and return the first line of the reply."""
    try:
        import urllib.request as _ur
        body = json.dumps({"message": question,
                           "use_cli": True, "use_kernel": False,
                           "use_wisdom": False}).encode()
        req = _ur.Request("http://127.0.0.1:8765/api/f47_chat",
                          data=body, method="POST",
                          headers={"Content-Type": "application/json"})
        with _ur.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode())
        layers = d.get("layers", {})
        reply = (layers.get("claude_cli") or layers.get("wren_local")
                 or d.get("render") or "(no advisor reply)").strip()
        first = reply.splitlines()[0] if reply else "(empty)"
        return first[:300]
    except Exception as e:
        return f"(wren consult failed: {str(e)[:120]})"


def consult_provider(question: str, provider: str = "deepseek") -> str:
    """Direct provider call (deepseek or openai) — no Auger persona."""
    try:
        model = "deepseek-chat" if provider == "deepseek" else "gpt-4o-mini"
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_consult_external.py"),
             "--provider", provider, "--model", model,
             "--reason", "start_job_advisor_backup",
             "--max-tokens", "120",
             "--prompt", question],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        if r.returncode != 0:
            return f"({provider} error: {r.stderr.strip()[-120:]})"
        # Tool prints framed header + reply between separator lines (━ x 56)
        out = r.stdout
        parts = out.split("━" * 56)
        # The reply is between the 2nd and 3rd separator
        if len(parts) >= 4:
            reply = parts[2].strip()
            return reply.splitlines()[0][:300] if reply else "(empty)"
        # Fallback: take last non-empty line
        lines = [l for l in out.strip().splitlines() if l.strip()]
        return lines[-1][:300] if lines else f"({provider} empty)"
    except Exception as e:
        return f"({provider} failed: {str(e)[:120]})"


def consult_auger(question: str) -> str:
    """Call tools/qsb_consult_external via Auger persona."""
    try:
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_consult_external.py"),
             "--provider", "openai", "--model", "gpt-4o-mini",
             "--reason", "start_job_advisor",
             "--max-tokens", "120",
             "--prompt", f"As Auger, Wren's bounded advisor. Question: {question}"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        if r.returncode != 0:
            return f"(auger error: {r.stderr.strip()[-120:]})"
        out = r.stdout
        parts = out.split("━" * 56)
        if len(parts) >= 4:
            return parts[3].strip().splitlines()[0][:300]
        return out.strip().splitlines()[-1][:300] if out.strip() else "(auger empty)"
    except Exception as e:
        return f"(auger failed: {str(e)[:120]})"


def dispatch_teammate(worker: str, task: str, timeout: int = 60) -> bool:
    """Fire off ONE Wren team worker on a one-line task."""
    team_tool = ROOT / "tools/qsb_wren_team.py"
    if not team_tool.exists():
        return False
    try:
        # Run in background so it doesn't block the start
        env = dict(os.environ); env["QSB_WREN_DISPATCH_FORCE"] = "1"
        subprocess.Popen(
            [".venv/bin/python3", str(team_tool),
             "--worker", worker, "--task", task],
            cwd=str(ROOT), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=env)
        return True
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("title")
    p.add_argument("--question", required=True,
                   help="one-line yes/no/concern for the advisor")
    p.add_argument("--advisor", default="wren",
                   choices=["wren", "auger", "deepseek", "openai"],
                   help="primary advisor")
    p.add_argument("--backup-advisor", default=None,
                   choices=["wren", "auger", "deepseek", "openai"],
                   help="REQUIRED second advisor — Ross 2026-06-16: ideas need backup by another")
    p.add_argument("--teammate", default="forge",
                   choices=["pip", "forge", "mira", "bram", "cass"])
    p.add_argument("--task", default=None,
                   help="teammate task (default = title + audit framing)")
    args = p.parse_args()

    ts = _now()
    # Derive a stable short job_id
    job_id = "job_" + hashlib.sha1(
        f"{ts}|{args.title}".encode()).hexdigest()[:10]

    # Stage A: consult advisor (primary)
    def _consult(who):
        if who == "wren":
            return consult_wren(args.question)
        if who == "auger":
            return consult_auger(args.question)
        if who in ("deepseek", "openai"):
            return consult_provider(args.question, who)
        return f"(unknown advisor {who})"

    advisor_line = _consult(args.advisor)

    # Stage A2: backup advisor — Ross's rule, an idea needs backup by another
    if not args.backup_advisor:
        # default backup: if primary was wren, backup is deepseek; otherwise wren
        backup = "deepseek" if args.advisor == "wren" else "wren"
    else:
        backup = args.backup_advisor
    if backup == args.advisor:
        print("REFUSED: backup advisor must differ from primary", file=sys.stderr)
        sys.exit(2)
    backup_line = _consult(backup)
    # Both replies must be non-error for the job to be allowed to start.
    if advisor_line.startswith("(") or backup_line.startswith("("):
        print("REFUSED: one or both advisors returned an error;"
              f" primary={advisor_line!r} backup={backup_line!r}", file=sys.stderr)
        sys.exit(3)

    # Stage B: dispatch teammate in background
    team_task = args.task or (
        f"Watch the work on '{args.title}'. Read the last 10 lines of "
        f"data/registries/qsb_tower_activity_tail.jsonl and flag anything that "
        f"looks misaligned in 2 sentences.")
    dispatched = dispatch_teammate(args.teammate, team_task)

    # Stage C: stamp job_started with BOTH fields
    row = {
        "ts": ts, "kind": "job_started", "operator": "claude",
        "job_id": job_id, "title": args.title[:200],
        "advisor_consulted": f"{args.advisor}",
        "advisor_reply_first_line": advisor_line,
        "backup_advisor": backup,
        "backup_advisor_reply": backup_line,
        "approvals": 2,
        "team_dispatched": f"wren_team.{args.teammate}" if dispatched else "FAILED",
        "team_task": team_task[:300],
    }
    _stamp(REG / "qsb_f47_team_records.jsonl", row)
    _stamp(REG / "qsb_tower_activity_tail.jsonl", {
        "ts": ts, "event_kind": "job_started",
        "worker_id": "claude",
        "payload": {"job_id": job_id, "title": args.title[:120],
                     "advisor": args.advisor,
                     "teammate": args.teammate}})

    print(json.dumps({
        "job_id": job_id, "started_ts": ts,
        "advisor_reply_first_line": advisor_line,
        "team_dispatched": dispatched,
        "teammate": args.teammate,
    }, indent=2))


if __name__ == "__main__":
    main()
