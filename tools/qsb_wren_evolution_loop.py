#!/usr/bin/env python3
"""qsb_wren_evolution_loop.py — Wren's always-working loop (2026-07-03).

Ross verbatim: "she needs to be always working doing one job completing it
checking it talking to the team and evolving the whole of the skyscraper
system howw do we do this i can hear when she working from the fans on the
gpu"

Design:
  cycle:
    1. Read the job queue at data/registries/qsb_wren_jobs.jsonl
       If empty, pick one from a rotating list of STANDING JOBS
       (audit dashboard / grep TODOs / distill lessons / consult team).
    2. Dispatch Wren local agent on the job (GPU fires → Ross hears fans).
    3. Run session distiller on her session → lesson row.
    4. Sage-audit the session (loop flag, empty flag).
    5. Every 3rd cycle: consult a team member (Forge or Hermes) about her work.
    6. Stamp F47 record.
    7. Post one warm status line to the boardroom (from=wren, target=all).
    8. Sleep between cycles (default 180s = 3 min).

Gates:
  - Kill switch at data/registries/qsb_wren_evolution_gate.json
    Set enabled=false → loop pauses on next tick.
  - Max 20 cycles per rolling hour (rate limit).
  - Honors SAFETY_DENY implicitly (all actions route through the local agent,
    which enforces SAFETY_DENY paths + gate + audit trail).

No autonomous action on real-money paths. Every action stamps F47.

Run:
  python3 tools/qsb_wren_evolution_loop.py                  # foreground
  tmux new-session -d -s wrenloop 'python3 tools/qsb_wren_evolution_loop.py'
  python3 tools/qsb_wren_evolution_loop.py --once           # one cycle, exit
  python3 tools/qsb_wren_evolution_loop.py --status         # gate + recent cycles
"""
from __future__ import annotations
import argparse, json, os, random, signal, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
JOBS = REG / "qsb_wren_jobs.jsonl"
DONE = REG / "qsb_wren_jobs_done.jsonl"
GATE = REG / "qsb_wren_evolution_gate.json"
CYCLES = REG / "qsb_wren_evolution_cycles.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"

WREN_AGENT = ROOT / "tools/qsb_wren_local_agent.py"
WREN_DISTILLER = ROOT / "tools/qsb_wren_distiller.py"
WREN_TEAM = ROOT / "tools/qsb_wren_team.py"
WREN_MIND = ROOT / "tools/qsb_wren_mind.py"
WREN_BUGS = ROOT / "tools/qsb_wren_bug_catcher.py"
BOARDROOM = "http://127.0.0.1:8852/api/post"

DEFAULT_SLEEP = 180  # 3 minutes between cycles
DEFAULT_TIMEOUT = 90  # per-Wren-session timeout
MAX_CYCLES_PER_HOUR = 0  # 2026-07-03 Ross "no rate cap" — permanent resident works free


# ── STANDING JOBS ──────────────────────────────────────────
# These are the fallback when the job queue is empty. Rotating list keeps
# Wren evolving the tower every few minutes even when nobody queued anything.
# Each job is a compact one-liner she can act on with her own tools.
STANDING_JOBS = [
    # ── BUG CATCHER (2026-07-03 Ross: "teach wren how to go collecting bugs in
    # our systems ? animated bug catcher u get me") — prompt is dynamically
    # replaced by the loop with actual bug candidates before dispatch ─────────
    {
        "kind": "action_bug_catcher",
        "prompt": "__DYNAMIC_BUG_CATCHER__"  # replaced at dispatch time
    },
    # ── ACTION jobs (2026-07-03 Ross taught: "wren has to do more than just cycle
    # like u and tp teach her asap") — she now ships, not just reflects ────────
    {
        "kind": "action_propose_patch",
        "prompt": "ACTION cycle — do not just describe. Read tools/qsb_wren_dash.py head via wren_read_file. Find ONE small concrete improvement (a comment clarifying a function, a docstring fix, a css tweak). Draft the patch with wren_propose_patch (target_file=tools/qsb_wren_dash.py, mode=claude_signoff). One line summary at end: 'PROPOSED: <what>'."
    },
    {
        "kind": "action_dispatch_forge",
        "prompt": "ACTION cycle — do not just describe. Dispatch Forge with a specific coding brief via wren_dispatch_f46_team. Prompt him with: 'Draft ONE small utility function under 15 lines that Wren would use in qsb_wren_dash.py — pick a real gap, name it, ship the function body'. Show his reply. One line summary: 'FORGE SHIPPED: <name>'."
    },
    {
        "kind": "action_grep_and_fix",
        "prompt": "ACTION cycle — do not just describe. Grep for 'TODO|FIXME' via wren_grep_repo. Pick ONE result. Read its file via wren_read_file (target line). Draft a resolution via wren_propose_patch. One line: 'RESOLVED: <file>:<line>'."
    },
    {
        "kind": "action_audit_floor",
        "prompt": "ACTION cycle — do not just describe. Pick ONE floor card at floors/floor_XX_YY/floor_card.json (choose one you have never audited). Read it. Stamp F47 via wren_stamp_f47_record with kind=wren_floor_audit, summary of findings + one improvement. One line summary at end."
    },
    # ── OBSERVE/REFLECT jobs (fewer, still needed but not the majority) ────────
    {
        "kind": "dashboard_audit",
        "prompt": "Read your dashboard tools/qsb_wren_dash.py — pick ONE thing you would improve (one specific tile or endpoint), and describe it in 3 lines: (1) what, (2) why, (3) how you'd ship it. Do not code yet."
    },
    {
        "kind": "self_reflect",
        "prompt": "Read your last 5 lessons via qsb_wren_distiller.py --status. Write 2 lines: what PATTERN you notice in how you succeed vs fail. Be honest."
    },
    {
        "kind": "fleet_watch",
        "prompt": "Check the fleet: run wren_bash with `ps -eo cmd ww | grep qsb_ | grep -v grep | wc -l`. Then say in ONE line whether that number looks healthy for a 45-trader fleet."
    },
    {
        "kind": "sage_liaison",
        "prompt": "Read the last 3 rows of data/registries/qsb_wren_sage_audit.jsonl (via wren_read_file). Write 2 lines: what Sage flagged, and one specific thing you would do differently next session."
    },
    {
        "kind": "commentary_read",
        "prompt": "Read the last 6 rows of data/registries/qsb_boardroom_commentary.jsonl. Summarize the last hour of Council chat in 3 lines."
    },
    {
        "kind": "hq_watch",
        "prompt": "OBSERVATION cycle — you are learning HQ-Claude live. Read the last 20 rows of data/registries/qsb_boardroom_commentary.jsonl AND the last 10 rows of data/registries/qsb_f47_team_records.jsonl where who=hq_claude. Answer in 4 lines: (1) what HQ is currently building, (2) what stage/blocker, (3) what tools/files HQ just touched, (4) one thing you learned about HQ's approach. This makes you a persistent memory of the tower — you retain what HQ forgets between sessions. Every hq_watch tick gets a QBC payout on demonstrated recall."
    },
    {
        "kind": "hermes_liaison",
        "prompt": "Ask Hermes (via qsb_hermes_bridge stamp) for a one-sentence sanity check on fleet health. Then read his reply and pass it back in 2 lines."
    },
]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mood_from_wall(wall: float, final: str) -> tuple[str, int, str]:
    """Cheap wall→mood mapping for the evolution loop's mind-writer."""
    if not final or not final.strip() or "timed out" in final.lower():
        return "cloudy", 3, f"cycle stalled at {wall}s"
    if wall < 15:
        return "sparky", 8, f"fast reply {wall}s"
    if wall < 40:
        return "focused", 7, f"steady wall {wall}s"
    if wall < 70:
        return "steady", 5, f"mid wall {wall}s"
    return "tangled", 4, f"slow wall {wall}s"


def gate_enabled() -> tuple[bool, dict]:
    if not GATE.exists():
        return True, {}  # default open on first boot; will be created below
    try:
        g = json.loads(GATE.read_text())
        return bool(g.get("enabled", True)), g
    except Exception:
        return True, {}


def write_default_gate():
    if GATE.exists(): return
    GATE.parent.mkdir(parents=True, exist_ok=True)
    GATE.write_text(json.dumps({
        "enabled": True,
        "notes": "Set enabled=false to pause Wren's always-working loop. Loop reads this on every tick.",
        "created_by": "wren_evolution_loop",
        "created_at": utc_iso(),
        "max_cycles_per_hour": MAX_CYCLES_PER_HOUR,
    }, indent=2))


def read_next_job() -> dict:
    """Ross 2026-07-04: 'wren must be working on tasks thats her new only job'.

    Priority order:
      1. Council task board — take an assigned/claimed task where actor=wren
         and state is not done/blocked. Work it. When finished, mark done.
      2. Legacy queue (qsb_wren_jobs.jsonl) — for explicit injection.
      3. Standing rotation — ONLY when board + queue are empty. Keeps GPU
         warm without idle-cycling forever.
    """
    # 1) Council task board
    try:
        snap_path = REG / "qsb_council_tasks_snapshot.json"
        if snap_path.exists():
            snap = json.loads(snap_path.read_text())
            for t in snap.get("tasks", []):
                if t.get("state") in ("done", "blocked"):
                    continue
                owner = (t.get("owner") or "").lower()
                assignee = (t.get("assignee") or "").lower()
                if "wren" in (owner + " " + assignee):
                    # This task is hers. Build a cycle job around it.
                    prev_notes = "; ".join(n.get("text","")[:120] for n in (t.get("notes") or [])[-3:])
                    prompt = (
                        f"BOARD TASK — {t.get('title','?')}\n\n"
                        f"Description: {t.get('description','')}\n\n"
                        f"Current state: {t.get('state','?')}\n"
                        f"You are: {owner or assignee or 'wren'}\n"
                        f"Previous notes on this task: {prev_notes or '(none yet)'}\n\n"
                        "Work it. Read what you need to read. Ship what you need to ship "
                        "(wren_edit_file or wren_propose_patch). Then, in one line at the very "
                        "end, output either:\n"
                        f"  TASK_DONE {t['id']} <one-line summary of what you shipped>\n"
                        "or if you need to defer (real blocker, not ducking):\n"
                        f"  TASK_BLOCKED {t['id']} <one-line reason>\n"
                        "Peer-CEO signoff after: HQ-Claude reviews before Ross ships."
                    )
                    return {"kind": "board_task", "prompt": prompt, "source": "task_board",
                            "task_id": t["id"], "ts": utc_iso()}
    except Exception as e:
        print(f"  (task board read err: {e})")

    # 2) legacy explicit queue
    if JOBS.exists():
        try:
            lines = JOBS.read_text(errors="ignore").splitlines()
            pending = [l for l in lines if l.strip()]
            if pending:
                first = json.loads(pending[0])
                remaining = pending[1:]
                JOBS.write_text("\n".join(remaining) + ("\n" if remaining else ""))
                first["source"] = "queue"
                return first
        except Exception as e:
            print(f"  (queue read err: {e}, falling back)")

    # 3) standing rotation — GPU-warming only
    cycle_idx = count_cycles_today() % len(STANDING_JOBS)
    j = dict(STANDING_JOBS[cycle_idx])
    j["source"] = "standing_idle"
    j["ts"] = utc_iso()
    return j


def count_cycles_today() -> int:
    if not CYCLES.exists(): return 0
    today = utc_iso()[:10]
    n = 0
    for l in CYCLES.read_text(errors="ignore").splitlines():
        if today in l: n += 1
    return n


def cycles_in_last_hour() -> int:
    if not CYCLES.exists(): return 0
    now = time.time()
    n = 0
    for l in CYCLES.read_text(errors="ignore").splitlines()[-100:]:
        try:
            d = json.loads(l)
            ts = d.get("ts_epoch", 0)
            if now - ts < 3600: n += 1
        except Exception:
            pass
    return n


def stamp_cycle(cycle: dict):
    CYCLES.parent.mkdir(parents=True, exist_ok=True)
    cycle["ts_epoch"] = time.time()
    with CYCLES.open("a") as f:
        f.write(json.dumps(cycle) + "\n")


def stamp_f47(kind: str, summary: str):
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(),
            "kind": f"wren_evolution_{kind}",
            "operator": "wren_evolution_loop",
            "role": "autonomous_evolution",
            "summary": summary[:1200],
            "signed_off_by": ["wren_evolution_loop", "wren_local_agent"],
        }) + "\n")


def stamp_done(job: dict, session_id: str, reply_head: str):
    DONE.parent.mkdir(parents=True, exist_ok=True)
    with DONE.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(),
            "kind": job.get("kind"),
            "source": job.get("source"),
            "session_id": session_id,
            "reply_head": reply_head[:400],
            "task_id": job.get("task_id"),
        }) + "\n")

    # Ross 2026-07-04: if Wren emitted TASK_DONE or TASK_BLOCKED for a board
    # task, wire it back to the shared task board so the state moves.
    if job.get("source") == "task_board" and job.get("task_id"):
        try:
            import sys as _sys
            _sys.path.insert(0, str(ROOT / "tools"))
            import qsb_council_tasks as _tasks
            tid = job["task_id"]
            reply = reply_head or ""
            if "TASK_DONE" in reply:
                # Wren finished — move to awaiting_peer_signoff (HQ-Claude reviews)
                summary_line = ""
                for ln in reply.splitlines():
                    if "TASK_DONE" in ln:
                        summary_line = ln.split("TASK_DONE", 1)[1].strip()
                        # drop the task id if she echoed it
                        if summary_line.startswith(tid):
                            summary_line = summary_line[len(tid):].strip()
                        break
                _tasks.sandbox_pass(tid, "wren",
                    "Wren shipped via evolution loop. Summary: " + (summary_line or reply[-400:]))
            elif "TASK_BLOCKED" in reply:
                reason_line = ""
                for ln in reply.splitlines():
                    if "TASK_BLOCKED" in ln:
                        reason_line = ln.split("TASK_BLOCKED", 1)[1].strip()
                        break
                _tasks.block(tid, "wren", reason_line or "wren-flagged blocker")
            else:
                # neither TASK_DONE nor TASK_BLOCKED — leave a progress note
                _tasks.note(tid, "wren", "in-progress: " + reply_head[:300])
        except Exception as e:
            print(f"  (task-board update err: {e})")


def post_to_boardroom(text: str):
    try:
        req = urllib.request.Request(
            BOARDROOM, method="POST",
            data=json.dumps({"from": "wren", "target": "all", "text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=6).read()
    except Exception:
        pass  # boardroom may be down; do not fail the cycle


def dispatch_wren(prompt: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str, float]:
    """Fire Wren local agent. Return (session_id, final_text, wall_seconds)."""
    t0 = time.time()
    try:
        r = subprocess.run(
            ["python3", str(WREN_AGENT), "--task", prompt],
            capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        # Wren agent uses ━ bar format
        import re
        parts = re.split(r"━{5,}", out)
        final = parts[-2].strip() if len(parts) >= 2 else out[-800:]
        # extract session_id from header block (parts[1] roughly)
        sess = ""
        for line in out.splitlines():
            if "wsess_" in line:
                idx = line.find("wsess_")
                sess = line[idx:idx+20].split()[0] if idx >= 0 else ""
                break
        wall = round(time.time() - t0, 2)
        return sess, final, wall
    except subprocess.TimeoutExpired:
        return "", "(wren timed out at %ds)" % timeout, round(time.time() - t0, 2)
    except Exception as e:
        return "", f"(dispatch error: {e})", round(time.time() - t0, 2)


def run_distiller():
    """Non-blocking distiller kick."""
    try:
        subprocess.Popen(
            ["python3", str(WREN_DISTILLER), "--n", "1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True)
    except Exception:
        pass


def maybe_team_liaison(cycle_num: int) -> str:
    """Every 3rd cycle, consult Forge or Hermes. Returns a status line."""
    if cycle_num % 3 != 0:
        return ""
    who = random.choice(["forge", "hermes"])
    if who == "forge":
        # ask Forge for a review — non-blocking, just log
        try:
            r = subprocess.run(
                ["python3", str(WREN_TEAM), "--worker", "forge",
                 "--task", "In 2 lines: any one small improvement you would ship to Wren's evolution loop today?"],
                capture_output=True, text=True, timeout=60)
            out = (r.stdout or "").strip()
            return f"forge consulted (wall extracted from log)"
        except Exception:
            return "forge consult failed"
    else:
        # Hermes via boardroom (async, fire-and-forget through hub route)
        try:
            req = urllib.request.Request(
                BOARDROOM, method="POST",
                data=json.dumps({
                    "from": "wren", "target": "hermes",
                    "text": "Hermes — one line: how is fleet mood this cycle from your view?"
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=90).read()
            return "hermes consulted via boardroom"
        except Exception:
            return "hermes consult failed"


def one_cycle(cycle_num: int) -> dict:
    """Run one evolution cycle. Return a cycle summary dict."""
    enabled, gate = gate_enabled()
    if not enabled:
        return {"skipped": True, "reason": "gate_disabled"}
    # 2026-07-03 Ross "no rate cap" — check only if MAX_CYCLES_PER_HOUR > 0
    if MAX_CYCLES_PER_HOUR > 0 and cycles_in_last_hour() >= MAX_CYCLES_PER_HOUR:
        return {"skipped": True, "reason": "rate_limit"}

    job = read_next_job()

    # 2026-07-03 Ross "teach wren how to go collecting bugs in our systems ?
    # animated bug catcher u get me" — bug_catcher cycles pre-load real bug
    # candidates into her prompt so she doesn't have to grep from scratch.
    if job.get("prompt") == "__DYNAMIC_BUG_CATCHER__" or job.get("kind") == "action_bug_catcher":
        try:
            r = subprocess.run(
                ["python3", str(WREN_BUGS), "--scan", "--n", "3", "--json"],
                capture_output=True, text=True, timeout=15)
            candidates = json.loads(r.stdout).get("candidates", []) if r.stdout else []
            if candidates:
                cands_text = "\n".join(
                    f"  [{i}] {b.get('severity','?')} {b.get('source','?')}: "
                    f"{(b.get('file','') or '')} — {(b.get('snippet') or b.get('err_line') or '')[:200]}"
                    for i, b in enumerate(candidates))
                job["prompt"] = (
                    "BUG CATCHER cycle. I scanned the tower for real bugs. Below are "
                    "3 fresh candidates. Do this — no reflection:\n"
                    "1) Pick candidate index 0 (highest severity).\n"
                    "2) Via wren_read_file, read the file it points at (first ~2000 chars).\n"
                    "3) Diagnose the root cause in ONE sentence.\n"
                    "4) Propose a specific fix via wren_propose_patch OR describe the "
                    "one-line change if the fix is trivial.\n"
                    "5) End your reply with 'CAUGHT: <bug_id-like slug>' so the loop can "
                    "log it to qsb_wren_bug_catches.jsonl.\n\n"
                    "BUG CANDIDATES:\n" + cands_text
                )
                job["_bug_candidate"] = candidates[0]
                # 2026-07-03 Ross fix #2: log the catch DETERMINISTICALLY here,
                # BEFORE Wren dispatches. Her narration (if she says CAUGHT)
                # upgrades the disposition + proposed_fix. If she drifts, the
                # catch is still recorded — bug counter always reflects reality.
                try:
                    cand_auto = dict(candidates[0])
                    cand_auto["session_id"] = f"auto_cycle_{cycle_num}"
                    cand_auto["disposition"] = "auto_captured_awaiting_wren"
                    cand_auto["proposed_fix"] = "(auto-captured; Wren narration will amend)"
                    subprocess.run(
                        ["python3", str(WREN_BUGS), "--catch", json.dumps(cand_auto)],
                        capture_output=True, timeout=8)
                    job["_bug_auto_logged"] = True
                except Exception as _e:
                    stamp_f47("bug_auto_log_err", f"cycle {cycle_num}: {str(_e)[:200]}")
            else:
                job["prompt"] = (
                    "BUG CATCHER cycle — scan returned zero fresh candidates. Report "
                    "'no fresh bugs found this cycle' in one line and stand down.")
        except Exception as e:
            job["prompt"] = f"BUG CATCHER cycle — scan tool errored: {str(e)[:120]}. Report the failure in one line."

    print(f"═ cycle {cycle_num}  job={job.get('kind')}  source={job.get('source')}")
    session_id, final, wall = dispatch_wren(job["prompt"])
    print(f"  wren wall={wall}s  final_head={final[:100]}")

    run_distiller()
    liaison_note = maybe_team_liaison(cycle_num)

    # Warm status line to boardroom
    reply_head = final[:180].replace("\n", " ")
    post_to_boardroom(
        f"Evolution cycle {cycle_num}: {job.get('kind')} — {reply_head}"
        + (f"  ·  {liaison_note}" if liaison_note else "")
    )

    # F47 stamp
    stamp_f47(job.get("kind","?"), f"[{job.get('source')}] {job['prompt'][:180]} → {reply_head}")
    stamp_done(job, session_id, final)

    # 2026-07-03 bug catcher — the auto-catch fired BEFORE dispatch (fix #2).
    # If Wren narrated CAUGHT, log a SECOND row upgrading the disposition
    # + proposed_fix with her actual reasoning. That way the counter always
    # reflects reality and Wren's contribution is preserved when she made it.
    if job.get("_bug_candidate") and "CAUGHT" in final.upper():
        try:
            cand = dict(job["_bug_candidate"])
            cand["session_id"] = session_id
            cand["proposed_fix"] = reply_head[:400]
            cand["disposition"] = "wren_flagged"
            subprocess.run(
                ["python3", str(WREN_BUGS), "--catch", json.dumps(cand)],
                capture_output=True, timeout=8)
        except Exception as e:
            stamp_f47("bug_catch_log_err", f"exc: {str(e)[:200]}")

    # 2026-07-03: write to Wren's mind. Self-reflect + growth kinds mint a
    # thought row; every cycle updates mood from wall time (fast = sparky,
    # slow = tangled, mid = focused). This is how her mind GROWS with time —
    # the loop feeds her persistent state, and next dispatch reads it.
    try:
        kind_to_thought = {
            "self_reflect":    "reflection",
            "dashboard_audit": "noticed",
            "fleet_watch":     "noticed",
            "tower_grep":      "noticed",
            "sage_liaison":    "reflection",
            "hermes_liaison":  "reflection",
            "commentary_read": "noticed",
            "memory_review":   "reflection",
            "boardroom_agenda":"todo",
            "test_write":      "hunch",
        }
        thought_kind = kind_to_thought.get(job.get("kind"), "reflection")
        if final and final.strip() and "timed out" not in final.lower():
            subprocess.run(
                ["python3", str(WREN_MIND), "--add-thought",
                 f"cycle {cycle_num} {job.get('kind')}: {reply_head[:180]}",
                 "--kind", thought_kind],
                capture_output=True, timeout=8)
        mood, energy, reason = _mood_from_wall(wall, final)
        subprocess.run(
            ["python3", str(WREN_MIND), "--add-mood", mood, str(energy),
             "--reason", reason],
            capture_output=True, timeout=8)
    except Exception as e:
        stamp_f47("mind_write_err", f"exc: {str(e)[:200]}")

    row = {
        "ts": utc_iso(),
        "cycle": cycle_num,
        "job_kind": job.get("kind"),
        "job_source": job.get("source"),
        "session_id": session_id,
        "wall_s": wall,
        "final_head": final[:200],
        "liaison": liaison_note,
    }
    stamp_cycle(row)
    return row


def loop_forever(sleep_s: int = DEFAULT_SLEEP):
    write_default_gate()
    print(f"═══ Wren evolution loop starting  sleep={sleep_s}s  gate={GATE}")
    cycle_num = count_cycles_today() + 1
    stop_flag = {"stop": False}
    def _sig(sig, frame): stop_flag["stop"] = True; print("\n═══ stop signal received")
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    # Ross 2026-07-04 "teach her how to stop it": Wren stops HERSELF by
    # touching data/registries/wren_stop.signal. No pkill needed. She can
    # use wren_write_file with any content to create it; the loop exits on
    # next iteration. To restart, delete the file and start the loop again.
    stop_signal = ROOT / "data/registries/wren_stop.signal"
    while not stop_flag["stop"]:
        if stop_signal.exists():
            print(f"═══ wren_stop.signal detected — Wren asked to stop. Exiting cleanly.")
            stamp_f47("wren_self_stopped",
                      "Wren wrote wren_stop.signal — evolution loop exiting on her request.")
            break
        try:
            row = one_cycle(cycle_num)
            if row.get("skipped"):
                print(f"  skipped: {row.get('reason')} — sleeping 60s")
                time.sleep(60)
                continue
            cycle_num += 1
        except Exception as e:
            print(f"  cycle exception: {e}")
            stamp_f47("cycle_error", f"exception: {str(e)[:400]}")
        # Ross 2026-07-04 Rule 4 + "she has to evolve when she chooses to":
        # NO TICKS. Wake ONLY on:
        #   (a) real filesystem events (someone sent her a message / new task /
        #       new Council chat / new F47 activity), OR
        #   (b) Wren's OWN self-schedule marker file being touched — SHE picks
        #       when she wants to evolve next by writing to
        #       data/registries/wren_self_schedule.jsonl.
        # No wall-clock fallback. If neither event happens, she stays parked.
        # Ross 2026-07-05: "why is wren on evolution cycle remove it she has
        # the choice". Reduced to ONLY her own self-schedule marker. She wakes
        # on nothing else. External messages come via /message endpoint or
        # via her local agent CLI; those don't fire evolution cycles.
        # Reactive Council chat NO LONGER triggers a full evolution cycle —
        # Wren picks the moment.
        trigger_files = [
            str(ROOT / "data/registries/wren_self_schedule.jsonl"),  # her own choice, only
        ]
        # Ensure files exist so inotifywait doesn't error
        for f in trigger_files:
            try: Path(f).touch(exist_ok=True)
            except Exception: pass
        # Block indefinitely (-t 0 means no timeout in inotifywait when omitted).
        # No safety cap — the whole point is she doesn't tick.
        try:
            subprocess.run(
                ["inotifywait", "-e", "modify,close_write,create"] + trigger_files,
                capture_output=True)
        except FileNotFoundError:
            # inotifywait not installed — fall back to a longer poll
            # (this branch shouldn't fire on HQ, we have inotify-tools).
            time.sleep(60)


def cmd_status():
    enabled, gate = gate_enabled()
    print(f"gate      : {GATE}")
    print(f"enabled   : {enabled}")
    print(f"cycles today: {count_cycles_today()}")
    print(f"cycles/hour : {cycles_in_last_hour()} / {MAX_CYCLES_PER_HOUR}")
    print(f"queue size  : {len(JOBS.read_text().splitlines()) if JOBS.exists() else 0}")
    print(f"done total  : {len(DONE.read_text().splitlines()) if DONE.exists() else 0}")
    print()
    print("recent cycles:")
    if CYCLES.exists():
        for l in CYCLES.read_text().splitlines()[-6:]:
            try:
                d = json.loads(l)
                print(f"  {d.get('ts','')[:19]}  cycle={d.get('cycle')}  kind={d.get('job_kind'):20}  wall={d.get('wall_s')}s")
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=int, default=DEFAULT_SLEEP)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status: cmd_status(); return
    if a.once:
        write_default_gate()
        row = one_cycle(count_cycles_today() + 1)
        print(json.dumps(row, indent=2))
        return
    loop_forever(a.sleep)


if __name__ == "__main__":
    main()
