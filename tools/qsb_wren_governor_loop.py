#!/usr/bin/env python3
"""qsb_wren_governor_loop.py — Wren's continuous MANAGEMENT / GOVERNOR loop.

Governor upgrade (2026-07-30). Ross: "she must be working ALL the time — not
just on tasks but RUNNING the whole tower. Any idle time she's LEARNING what's
going on; any other time she's MANAGING."

One tick:
  1. SURVEY   — skill tower_survey (whole-tower live state).
  2. DETECT   — skill governor_scan (ranked, de-duped agenda of what needs doing).
  3. DECIDE+ACT — hand the survey + scan to Wren's REAL model (local agent) and
     let her reason over the real findings and CREATE real council tasks
     (wren_create_council_task) for the top NEW findings. This is her model
     managing over real state — no scripted/canned tasks (R01). If there is NO
     new actionable finding, she instead LEARNS: she studies one floor she has
     not yet studied (tower_survey floor=N) and records what she learned.
  4. TRACK    — stamp an F47 governor_tick row + append a cycle record.

Pacing / safety:
  - Kill switch: data/registries/qsb_wren_governor_gate.json enabled=false.
  - Default 900s (15 min) between ticks so it does not hammer the GPU.
  - Non-autonomous w.r.t. real-world actions: Wren only books council tasks and
    studies floors. She never executes real-world actions or flips gates — the
    local agent enforces SAFETY_DENY + gate + audit on every call.
  - Rotating "study cursor" so idle ticks cover every floor over time.

Run:
  python3 tools/qsb_wren_governor_loop.py --once      # one tick, exit
  python3 tools/qsb_wren_governor_loop.py --status     # gate + last ticks
  python3 tools/qsb_wren_governor_loop.py              # continuous (systemd)
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
GATE = REG / "qsb_wren_governor_gate.json"
CYCLES = REG / "qsb_wren_governor_cycles.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
STUDY_CURSOR = REG / "qsb_wren_governor_study_cursor.json"
WREN_AGENT = ROOT / "tools/qsb_wren_local_agent.py"
FLOOR_INDEX = REG / "qsb_floor_activity_index.json"

DEFAULT_SLEEP = 900          # 15 min between ticks — paced, GPU-friendly
DEFAULT_MODEL = "qwen2.5:14b"
SESSION_TIMEOUT = 420        # per governor session


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(p, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def gate_open() -> bool:
    g = _load(GATE)
    if g is None:
        # default-open with a self-written gate so Ross can flip it off
        try:
            GATE.write_text(json.dumps({
                "enabled": True, "authored_by": "Claude governor upgrade",
                "ts": utc(),
                "note": "Wren's management/governor loop. Flip enabled=false to pause.",
                "sleep_s": DEFAULT_SLEEP,
            }, indent=2))
        except Exception:
            pass
        return True
    return bool(g.get("enabled", True))


def _run_skill(name: str, params: dict | None = None) -> dict:
    """Run a read skill in-process for the loop's own survey/scan."""
    skill_dir = ROOT / "skills/wren" / name
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"gov_skill_{name}", skill_dir / "skill.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(**(params or {}))


def _next_study_floor() -> int:
    """Rotate through floor numbers so idle ticks eventually study every floor."""
    idx = _load(FLOOR_INDEX, {}) or {}
    floors = sorted(int("".join(c for c in k if c.isdigit()) or -1)
                    for k in (idx.get("floors") or {}))
    floors = [f for f in floors if f >= 0]
    cur = _load(STUDY_CURSOR, {"i": 0}) or {"i": 0}
    i = cur.get("i", 0) % max(1, len(floors))
    fl = floors[i] if floors else 1
    try:
        STUDY_CURSOR.write_text(json.dumps({"i": (i + 1) % max(1, len(floors)), "last": fl}))
    except Exception:
        pass
    return fl


def _wren(task: str, model: str) -> str:
    """Invoke Wren's real local agent (her model reasons + acts)."""
    try:
        r = subprocess.run(
            ["python3", str(WREN_AGENT), "--model", model, "--task", task],
            capture_output=True, text=True, timeout=SESSION_TIMEOUT, cwd=str(ROOT))
        return (r.stdout or "").strip() or (r.stderr or "").strip()[:400]
    except subprocess.TimeoutExpired:
        return "(governor session timed out)"
    except Exception as e:
        return f"(governor session error: {e})"


def tick(model: str = DEFAULT_MODEL) -> dict:
    survey = _run_skill("tower_survey")
    scan = _run_skill("governor_scan")
    new_findings = [f for f in scan.get("findings", []) if not f.get("already_on_board")]
    mode = "MANAGE" if new_findings else "LEARN"

    if mode == "MANAGE":
        top = new_findings[:3]
        agenda = "\n".join(
            f"  - [{f.get('kind')}] {f.get('suggested_task_title')} :: {f.get('detail','')[:140]}"
            for f in top)
        task = (
            "GOVERNOR TICK. You are governing the whole tower. Here is the REAL live "
            f"state (from tower_survey): active={survey.get('active_floors')} "
            f"idle={survey.get('idle_floors')} skeleton_cards={survey.get('skeleton_cards')} "
            f"board open={survey.get('board',{}).get('open')} "
            f"blocked={survey.get('board',{}).get('blocked')} "
            f"open_worker_needs={survey.get('worker_needs_open')}.\n"
            "governor_scan found these NEW things that need doing (not yet on the board):\n"
            f"{agenda}\n\n"
            "For EACH of these, create a real council task with wren_create_council_task "
            "using that exact title. Then reply in ONE short paragraph naming the task IDs "
            "you created and the tower state. Do not invent findings — act only on these."
        )
    else:
        fl = _next_study_floor()
        task = (
            "GOVERNOR TICK — no new management findings, so LEARN. Run skill tower_survey "
            f"with floor={fl} to study that floor, then reply in TWO short lines: what that "
            "floor is (label + active/idle + staffing signal) and one thing you now understand "
            "about it. Real data only."
        )

    reply = _wren(task, model)
    row = {
        "ts": utc(), "mode": mode, "model": model,
        "active": survey.get("active_floors"), "idle": survey.get("idle_floors"),
        "skeleton_cards": survey.get("skeleton_cards"),
        "new_findings": len(new_findings),
        "studied_floor": (None if mode == "MANAGE" else _load(STUDY_CURSOR, {}).get("last")),
        "reply_head": reply[:600],
    }
    try:
        with CYCLES.open("a") as f:
            f.write(json.dumps(row) + "\n")
        with F47.open("a") as f:
            f.write(json.dumps({
                "ts": utc(), "kind": "governor_tick", "by": "wren", "mode": mode,
                "new_findings": len(new_findings),
                "text": f"Governor tick ({mode}): {reply[:200]}",
            }) + "\n")
    except Exception:
        pass
    return row


def status():
    g = _load(GATE, {"enabled": True})
    print("gate:", json.dumps(g, indent=2))
    if CYCLES.exists():
        lines = CYCLES.read_text().splitlines()[-5:]
        print("\nlast ticks:")
        for l in lines:
            try:
                d = json.loads(l)
                print(f"  {d['ts']} {d['mode']:7s} new={d.get('new_findings')} "
                      f"skel={d.get('skeleton_cards')} :: {d.get('reply_head','')[:90]}")
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sleep", type=int, default=None)
    a = ap.parse_args()
    if a.status:
        status()
        return
    if a.once:
        if not gate_open():
            print("governor gate CLOSED — not ticking")
            return
        print(json.dumps(tick(a.model), indent=2))
        return
    # continuous
    while True:
        if gate_open():
            try:
                r = tick(a.model)
                print(f"[{r['ts']}] {r['mode']} new={r['new_findings']}", flush=True)
            except Exception as e:
                print(f"[{utc()}] tick error: {e}", flush=True)
        else:
            print(f"[{utc()}] gate closed, idle", flush=True)
        sleep_s = a.sleep or (_load(GATE, {}) or {}).get("sleep_s", DEFAULT_SLEEP)
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()
