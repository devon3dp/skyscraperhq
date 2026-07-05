#!/usr/bin/env python3
"""qsb_iquest_code_review.py — iquest-coder:40b reviews recent code changes.
Per Ross 'wire them all in' + DeepSeek signoff. Cadence: hourly via heartbeat.
Reads last 5 git status entries (or recent .py mtime tail), asks iquest to gotcha-catch.
"""
import argparse, json, subprocess, time, glob
from pathlib import Path
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
def main():
    p = argparse.ArgumentParser(); p.add_argument("--quiet", action="store_true")
    a = p.parse_args()
    # Find 5 most recently modified .py files in tools/ (excludes pycache)
    files = sorted(glob.glob(str(ROOT/"tools/*.py")), key=lambda f: -Path(f).stat().st_mtime)[:5]
    snippets = []
    for f in files[:3]:  # top 3 only — keep brief small
        try:
            txt = Path(f).read_text()[:1500]
            snippets.append(f"=== {Path(f).name} (head 1500ch) ===\n{txt}")
        except Exception:
            pass
    if not snippets:
        if not a.quiet: print("no code to review")
        return
    prompt = ("You are iquest-coder (40B Llama coding specialist). Review these "
              "3 recent tool files. Flag up to 3 GOTCHAS (bug, race, missing error "
              "handle). One line each: 'GOTCHA: <file> — <issue>'. If clean: 'CLEAN'.\n\n"
              + "\n\n".join(snippets))
    t = time.time()
    r = subprocess.run(
        ["python3", "tools/qsb_local_agent_call.py",
          "--model", "iquest-coder-v1:40b-instruct",
          "--prompt", prompt[:7000]],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )
    reply = ""
    if r.returncode == 0 and r.stdout.strip():
        try:
            reply = json.loads(r.stdout).get("reply", r.stdout)[:1500]
        except Exception:
            reply = r.stdout[:1500]
    else:
        reply = f"(rc={r.returncode}) {r.stderr[:200]}"
    gotcha_n = sum(1 for ln in reply.splitlines() if "GOTCHA:" in ln)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": "iquest_code_review_40b", "kind": "scheduled_review",
            "role": "iquest-coder:40b", "subject": "hourly code review",
            "files_reviewed": [Path(f).name for f in files[:3]],
            "body": reply[:1500], "gotcha_count": gotcha_n,
            "wall_s": round(time.time()-t,1), "advisory_only": True}
    with open(F47, "a") as f: f.write(json.dumps(row, default=str) + "\n")
    if not a.quiet:
        print(f"OK code_review stamped — {gotcha_n} gotchas, {row['wall_s']}s")
        print(reply[:400])
if __name__ == "__main__":
    main()
