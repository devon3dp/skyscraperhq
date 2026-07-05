"""qsb_pull_when_done.py — watch for qwen2.5:32b finishing, then pull hermes3:70b.

Trigger: 2026-06-21 Ross "pull after this download finished make a reminder".

Polls `ollama list` every 60s. When `qwen2.5:32b` appears AND `hermes3:70b`
is absent, kicks off `ollama pull hermes3:70b` and exits. Stamps F47 at
start, kick-off, and completion. Safe to run repeatedly — it's a no-op
when target already installed.

Run:
    nohup python3 tools/qsb_pull_when_done.py > logs/pull_when_done.log 2>&1 &
"""
from __future__ import annotations
import datetime, json, subprocess, sys, time
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
F47 = REPO / "data/registries/qsb_f47_team_records.jsonl"
WAIT_FOR = "qwen2.5:32b"
PULL_TARGET = "hermes3:70b"
POLL_S = 60


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(kind: str, subject: str, detail: str) -> None:
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "kind": kind, "role": "claude",
            "subject": subject, "detail": detail,
        }) + "\n")


def installed_models() -> set[str]:
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    names = set()
    for line in r.stdout.splitlines()[1:]:
        if line.strip():
            names.add(line.split()[0])
    return names


def main() -> int:
    stamp("pull_when_done_started",
          f"watch for {WAIT_FOR} → pull {PULL_TARGET}",
          f"Polling every {POLL_S}s. Exits on success or if target already present.")
    print(f"[pull-when-done {now_iso()}] watching for {WAIT_FOR} → will pull {PULL_TARGET}")

    while True:
        try:
            models = installed_models()
        except Exception as e:
            print(f"[pull-when-done {now_iso()}] ollama list failed: {e}; retrying")
            time.sleep(POLL_S); continue

        if PULL_TARGET in models:
            print(f"[pull-when-done {now_iso()}] {PULL_TARGET} already installed — done.")
            stamp("pull_when_done_noop", PULL_TARGET, "Target already installed; nothing to do.")
            return 0

        if WAIT_FOR in models:
            print(f"[pull-when-done {now_iso()}] {WAIT_FOR} detected — kicking off {PULL_TARGET}")
            stamp("pull_when_done_kickoff", PULL_TARGET,
                  f"{WAIT_FOR} now present; starting `ollama pull {PULL_TARGET}`.")
            r = subprocess.run(["ollama", "pull", PULL_TARGET])
            ok = r.returncode == 0
            stamp("pull_when_done_finished", PULL_TARGET,
                  f"ollama pull {PULL_TARGET} exit={r.returncode}; ok={ok}")
            print(f"[pull-when-done {now_iso()}] pull exit={r.returncode}")
            return 0 if ok else 1

        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
