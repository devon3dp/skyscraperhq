"""
Wren TEAM bench — give pip / forge / mira / bram / cass each one canonical
task that matches their role and measure wall + reply length.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TEAM_TOOL = ROOT / "tools/qsb_wren_team.py"

TASKS = [
    ("pip", "assistant",
     "In ONE sentence, what does tools/qsb_telegram_receptionist.py do?"),
    ("forge", "code_drafter",
     "Write a 5-line Python function `count_lines(path)` that returns the number"
     " of lines in a file. Plain stdlib only. Output ONLY the function code."),
    ("mira", "reviewer",
     "Review this code for bugs: `def count_lines(p): return len(open(p).read().split('\\n'))`"
     " — flag any defects in 3 bullets."),
    ("bram", "triage",
     "Triage these three messages and label each [URGENT / NORMAL / LATER]:\n"
     "(1) Bot doesn't reply to texts.\n"
     "(2) Floor 47 dashboard widget is misaligned 2 px.\n"
     "(3) Trader logs show NaN PnL on EUR_USD position."),
    ("cass", "scribe",
     "Compose a 25-word session diary line for 2026-06-15 12:00 describing:"
     " heartbeat now auto-revives F25/F31/F38 loops + Wren team dispatches"
     " inside the tick. Begin with the ISO timestamp."),
]


def run(worker: str, task: str) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run(
            [".venv/bin/python3", str(TEAM_TOOL), "--worker", worker, "--task", task],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        wall = round(time.time() - t0, 2)
        out = (r.stdout or "")[-1500:]
        return {"worker": worker, "wall_s": wall, "exit_code": r.returncode,
                "reply": out}
    except subprocess.TimeoutExpired:
        return {"worker": worker, "wall_s": 60, "exit_code": -1, "reply": "TIMEOUT"}


def main() -> int:
    results = []
    for w, role, t in TASKS:
        print(f"--- {w} ({role}) ---", flush=True)
        r = run(w, t)
        r["role"] = role
        r["task_head"] = t[:120]
        # quality heuristic: reply has content + not error
        reply_len = len(r["reply"].strip())
        verdict = "PASS" if r["exit_code"] == 0 and reply_len > 30 else "FAIL"
        r["verdict"] = verdict
        print(f"   {w}: {verdict} wall={r['wall_s']}s reply_len={reply_len}",
              flush=True)
        results.append(r)

    summary = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": len(results),
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "fail": sum(1 for r in results if r["verdict"] == "FAIL"),
        "wall_total_s": round(sum(r["wall_s"] for r in results), 2),
        "by_worker": [{"worker": r["worker"], "role": r["role"],
                        "verdict": r["verdict"], "wall_s": r["wall_s"]}
                       for r in results],
    }
    print("\n" + json.dumps(summary, indent=2))
    out_dir = Path(__file__).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "team_bench_results.json").write_text(json.dumps({
        "summary": summary, "details": results,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
