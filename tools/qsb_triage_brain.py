#!/usr/bin/env python3
"""qsb_triage_brain.py — qwen3.5:9b triage brain (per persona in qsb_local_agent_call.py).

Per Ross "wire them all in" 2026-06-26. DeepSeek-signoff: qwen3.5:9b is wire-in #1.
Reads council brief + last 30 F47 rows + recent bus tail, asks qwen3.5:9b to flag
ANOMALIES (regression patterns, stuck workers, repeated errors, missed signoffs).
Writes one F47 row + emits triage_flag event to bus.

Run hourly via heartbeat OR on-demand from CLI.
"""
import argparse, json, subprocess, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
BUS_JOURNAL = ROOT / "data/registries/qsb_bus_journal.jsonl"


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def last_n_lines(path, n):
    if not path.exists():
        return []
    try:
        sz = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, sz - 32000))
            tail = f.read().decode("utf-8", errors="ignore").splitlines()
        return tail[-n:]
    except Exception:
        return []


def build_brief():
    """Compact context for qwen3.5:9b: 30 F47 rows + 30 bus events + tower state."""
    parts = ["# Triage brief", f"ts: {now_iso()}", ""]
    # F47 tail
    parts.append("## Last 30 F47 rows")
    for ln in last_n_lines(F47, 30):
        try:
            r = json.loads(ln)
            parts.append(f"- {r.get('ts','')[:16]}  {r.get('event','?')}: {(r.get('body','') or '')[:80]}")
        except Exception:
            continue
    # Bus event-name counts
    parts.append("\n## Last 200 bus events by name")
    from collections import Counter
    cnt = Counter()
    for ln in last_n_lines(BUS_JOURNAL, 200):
        try:
            cnt[json.loads(ln).get("name", "?")] += 1
        except Exception:
            pass
    for n, c in cnt.most_common(10):
        parts.append(f"- {c:4d}  {n}")
    return "\n".join(parts)


def call_triage_model(brief):
    """Call qwen3.5:9b via qsb_local_agent_call.py."""
    prompt = (
        brief + "\n\n"
        "You are the tower's triage brain. Read the brief above and flag up to 3 ANOMALIES "
        "(patterns suggesting bug, regression, stuck process, missed signoff, repeated failure). "
        "For each: ONE LINE — 'FLAG: <event-name> — <reason>'. If no anomalies, say 'CLEAN'."
    )
    try:
        r = subprocess.run(
            ["python3", "tools/qsb_local_agent_call.py",
              "--model", "qwen3.5:9b", "--prompt", prompt[:8000]],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                d = json.loads(r.stdout)
                return d.get("reply", r.stdout)[:2000]
            except Exception:
                return r.stdout[:2000]
        return f"(call failed rc={r.returncode}: {r.stderr[:200]})"
    except Exception as e:
        return f"(triage call exception: {e})"


def stamp_f47(reply):
    flag_count = sum(1 for ln in reply.splitlines() if ln.strip().startswith("FLAG:"))
    row = {
        "ts": now_iso(),
        "event": "triage_brain_qwen3_9b",
        "kind": "scheduled_triage",
        "role": "qwen3.5:9b",
        "subject": "5min triage sweep",
        "body": reply[:1500],
        "flag_count": flag_count,
        "advisory_only": True,
    }
    with open(F47, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return flag_count


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    brief = build_brief()
    reply = call_triage_model(brief)
    flags = stamp_f47(reply)
    if not args.quiet:
        print(f"OK triage stamped — {flags} flag(s)")
        print(reply[:400])


if __name__ == "__main__":
    main()
