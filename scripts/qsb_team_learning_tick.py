#!/usr/bin/env python3
"""Read latest model calls + roundtable outcomes → extract a lesson → append.
Append to shared_team_lessons.jsonl + each model's lessons.jsonl.
"""
import json
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SHARED = ROOT / "data/team_memory/shared"
LESSONS = SHARED / "shared_team_lessons.jsonl"
STATUS = ROOT / "data/registries/qsb_team_learning_status.json"

def utc(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_jsonl(p, n=20):
    if not p.exists(): return []
    try:
        out = []
        with p.open() as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    try: out.append(json.loads(ln))
                    except Exception: pass
        return out[-n:]
    except Exception:
        return []

def main():
    calls = []
    cp = ROOT / "data/registries/qsb_team_last_model_calls.json"
    if cp.exists():
        try: calls = json.loads(cp.read_text())
        except Exception: pass

    fail_rate_by_member = {}
    for c in calls[-20:]:
        m = c.get("member", "?")
        fail_rate_by_member.setdefault(m, {"n": 0, "fail": 0})
        fail_rate_by_member[m]["n"] += 1
        if not c.get("success"):
            fail_rate_by_member[m]["fail"] += 1

    lessons = []
    for m, st in fail_rate_by_member.items():
        n, fail = st["n"], st["fail"]
        rate = fail / n if n else 0.0
        if n >= 3 and rate >= 0.5:
            lessons.append({
                "ts": utc(),
                "scope": m,
                "lesson": f"{m} failed {fail}/{n} recent calls — check model loaded + timeout settings",
                "severity": "high" if rate >= 0.75 else "medium",
            })

    # Repeated F47 errors
    f47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
    if f47.exists():
        recent = load_jsonl(f47, n=100)
        ducks = [r for r in recent if r.get("kind") == "wren_duck"]
        if len(ducks) >= 2:
            lessons.append({
                "ts": utc(),
                "scope": "wren",
                "lesson": f"Wren has ducked {len(ducks)} times — sharpen prompt format + verify the model can do tool-call",
                "severity": "medium",
            })

    if lessons:
        LESSONS.parent.mkdir(parents=True, exist_ok=True)
        with LESSONS.open("a") as f:
            for l in lessons:
                f.write(json.dumps(l) + "\n")
        for l in lessons:
            scope = l["scope"]
            mp = ROOT / f"data/team_memory/{scope}/lessons.jsonl"
            if mp.parent.exists():
                with mp.open("a") as f:
                    f.write(json.dumps(l) + "\n")

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "ts": utc(),
        "lessons_appended": len(lessons),
        "failure_rates": fail_rate_by_member,
    }, indent=2))
    print(f"appended {len(lessons)} lessons; failure rates: {fail_rate_by_member}")

if __name__ == "__main__":
    main()
