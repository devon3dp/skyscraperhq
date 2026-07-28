#!/usr/bin/env python3
"""
qsb_codex_autorunner.py — Codex (OpenAI) autonomous task loop, GOVERNED.

Ross authorized the Codex provider-loop on 2026-07-28 (chose "all", including
"Codex task-driven loop (needs signoff)"). Per CLAUDE.md 2026-06-14 "bounded
provider-side worker agents": this is a DEDICATED Codex loop (NOT the tower
heartbeat), fully kill-switchable, and NON-SELF-VERIFYING.

Each tick (default 300s):
  1. Fail-closed on BOTH gates: qsb_provider_agentic_gate.json (enabled + budget)
     AND qsb_autorunner_gate.json (enabled). Also stop if remaining daily budget
     < per-session cap.
  2. Pick ONE real, open, unowned council task (reuse qsb_council_tasks.snapshot
     + the same real() filter the Wren autorunner uses). Cap Codex to 1 in-flight
     (owner=="codex") so he never fights Wren for the 3/CEO cap.
  3. Claim it as actor="codex", then run ONE bounded Codex session via
     tools/qsb_provider_agent.py against it (whitelisted read/propose/note tools).
  4. Codex ONLY claims + proposes + notes. He NEVER marks done / verifies. Wren's
     qsb-task-council-autorunner does the independent 2-CEO gene-pool quorum, so
     "taker can't sign off own" stays intact.

Kill switch: set enabled=false in EITHER gate file. systemd: qsb-codex-autorunner.service.
Run once for a proof:  python3 tools/qsb_codex_autorunner.py --once
Dry (no spend):        python3 tools/qsb_codex_autorunner.py --dry
"""
import os, sys, json, time, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
sys.path.insert(0, str(ROOT / "tools"))

AGENTIC_GATE = REG / "qsb_provider_agentic_gate.json"
AUTORUN_GATE = REG / "qsb_autorunner_gate.json"
ACT = REG / "qsb_codex_autorunner_activity.jsonl"
INTERVAL = int(os.environ.get("CODEX_INTERVAL", "300"))
MODEL = os.environ.get("CODEX_MODEL", "gpt-4o-mini")
ALLOWED = "qsb_read_registry,qsb_read_floor_card,qsb_grep_repo,qsb_propose_patch,qsb_council_task"


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def log(rec):
    rec["ts"] = utc()
    with open(ACT, "a") as f:
        f.write(json.dumps(rec) + "\n")


def _load(p, d):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return d


def gates_ok():
    ag = _load(AGENTIC_GATE, {})
    au = _load(AUTORUN_GATE, {})
    if not ag.get("enabled"):
        return False, "agentic gate disabled"
    if not au.get("enabled"):
        return False, "autorunner gate disabled"
    return True, ag


def budget_ok(ag):
    """Remaining daily agentic budget must cover at least one session."""
    try:
        import qsb_provider_agent as PA
        spent = PA.spent_today_usd()
        cap = float(ag.get("daily_budget_usd", 0))
        per_sess = float(ag.get("per_session_cap_usd", 0.25))
        return ((cap - spent) >= per_sess), spent, cap
    except Exception:
        return False, -1.0, -1.0


def real(t):
    tid = t.get("id", "") or ""
    title = (t.get("title") or "")
    return ("council_proof" not in (t.get("tags") or [])
            and "AUTO" not in title
            and "#TEST" not in title.upper()
            and not tid.startswith("t_test"))


def pick_task():
    import qsb_council_tasks as T
    tasks = T.snapshot().get("tasks", [])
    inflight = [t for t in tasks if t.get("owner") == "codex"
                and t.get("state") in ("claimed", "in_progress",
                                        "awaiting_verification", "awaiting_peer_signoff")]
    if inflight:
        return None, "codex already has 1 task in flight"
    opens = [t for t in tasks if t.get("state") == "open" and not t.get("owner") and real(t)]
    opens.sort(key=lambda t: t.get("created_at", ""))
    return (opens[0] if opens else None), ("picked" if opens else "no open unowned task")


def run_codex(task):
    """Claim as Codex, run ONE bounded provider session. Codex proposes + notes only."""
    import qsb_council_tasks as T
    tid = task["id"]
    title = task.get("title", "")
    desc = task.get("description", "") or ""
    T.claim(tid, "codex")
    system = ("You are Codex, the Floor 40 OpenAI worker on the QSB Tower. Read the task and "
              "produce a concrete artifact or code patch. You CANNOT self-approve or mark anything "
              "done — Wren plus a 2-CEO gene-pool quorum verify your work.")
    taskprompt = (f"Council task {tid}: {title}. {desc}\n"
                  "Steps: (1) use qsb_read_floor_card / qsb_read_registry / qsb_grep_repo for context, "
                  "(2) produce the improvement as a patch via qsb_propose_patch, "
                  f"(3) call qsb_council_task action=note task_id={tid} with a concise summary of what "
                  "you did. Do NOT attempt to verify or complete the task — leave that to Wren.")
    cmd = [sys.executable, str(ROOT / "tools" / "qsb_provider_agent.py"),
           "--provider", "openai", "--model", MODEL,
           "--system", system, "--task", taskprompt,
           "--allowed-tools", ALLOWED, "--session-id", f"codex_{tid}"]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        tail = (r.stdout or "")[-400:]
        try:
            T.note(tid, "codex", f"Codex session ran (rc={r.returncode}). {tail[:200]}")
        except Exception:
            pass
        return (r.returncode == 0), tail
    except subprocess.TimeoutExpired:
        return False, "timeout"


def tick(dry=False):
    ok, ag = gates_ok()
    if not ok:
        log({"tick": "skip", "reason": ag}); return
    bok, spent, cap = budget_ok(ag)
    if not bok:
        log({"tick": "skip", "reason": "budget", "spent": spent, "cap": cap}); return
    task, why = pick_task()
    if not task:
        log({"tick": "idle", "reason": why, "spent": round(spent, 4)}); return
    if dry:
        log({"tick": "dry", "would_claim": task["id"], "title": task.get("title", "")[:60],
             "spent": round(spent, 4), "cap": cap}); return
    log({"tick": "claim", "task_id": task["id"], "title": task.get("title", "")[:60]})
    done, tail = run_codex(task)
    log({"tick": "ran", "task_id": task["id"], "ok": done, "out": tail[:200]})


def main():
    log({"event": "codex_autorunner_start", "interval_s": INTERVAL, "model": MODEL, "pid": os.getpid()})
    while True:
        try:
            tick()
        except Exception as e:
            log({"tick": "error", "err": str(e)})
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--dry" in sys.argv:
        tick(dry=True)
        print("dry tick logged to", ACT)
    elif "--once" in sys.argv:
        tick()
        print("one tick logged to", ACT)
    else:
        main()
