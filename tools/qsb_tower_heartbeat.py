#!/usr/bin/env python3
"""qsb_tower_heartbeat.py — the Tower's runtime, independent of the terminal.

Ross 2026-06-12: "the skyscraper should still be running in the background
and your team should still be doing their tasks. So then when I wake up and
come back ... there's also lots of jobs already being done in the skyscraper."

This is Wren operating from F47 without a human in the loop. Every cycle the
heartbeat:
  · checks that essential daemons are alive (dashboard, lumen, vision, qualify
    loop, position monitor); restarts what died
  · runs the mass dispatch so the team logs visible work
  · refreshes the steward briefing
  · runs the qualification sweep (idempotent — already-certified workers skip)
  · refreshes OANDA position snapshot
  · stamps an F47 heartbeat record so progress is visible at wake
  · respects the safety envelope — no real-money trades, no autonomous
    deploys, no CLAUDE.md edits, no provider calls without authorization
    going through the existing bounded path

Run: nohup python3 tools/qsb_tower_heartbeat.py --interval 300 &
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


# ── daemons we keep alive ────────────────────────────────────────────
DAEMONS = [
    {
        "name": "dashboard",
        "port": 8765,
        "pgrep_pat": "src/dashboard/server.py",
        "launch": [".venv/bin/python3", "src/dashboard/server.py"],
        "log": "/tmp/skyscraper/dash.log",
    },
    {
        "name": "lumen",
        "port": 8848,
        "pgrep_pat": "qsb_lumen_serve.py",
        "launch": ["python3", "tools/qsb_lumen_serve.py"],
        "log": "/tmp/skyscraper/lumen.log",
    },
    {
        "name": "vision",
        "port": 8821,
        "pgrep_pat": "qsb_vision_floor.py",
        "launch": ["python3", "tools/qsb_vision_floor.py"],
        "log": "/tmp/skyscraper/vision.log",
    },
    {
        "name": "qualify_loop",
        "port": None,
        "pgrep_pat": "qsb_qualify_everyone.py --loop",
        "launch": ["python3", "tools/qsb_qualify_everyone.py", "--loop"],
        "log": "/tmp/skyscraper/qualify.log",
    },
    {
        "name": "f25_loop",
        "port": None,
        "pgrep_pat": "qsb_f25_worker_recruitment_loop.py",
        "launch": [".venv/bin/python3",
                   "tools/qsb_f25_worker_recruitment_loop.py"],
        "log": "logs/qsb_f25_loop.log",
    },
    {
        "name": "f31_loop",
        "port": None,
        "pgrep_pat": "qsb_f31_audit_ledger_loop.py",
        "launch": [".venv/bin/python3",
                   "tools/qsb_f31_audit_ledger_loop.py"],
        "log": "logs/qsb_f31_loop.log",
    },
    {
        "name": "f38_loop",
        "port": None,
        "pgrep_pat": "qsb_f38_sandbox_ops_loop.py",
        "launch": [".venv/bin/python3",
                   "tools/qsb_f38_sandbox_ops_loop.py"],
        "log": "logs/qsb_f38_loop.log",
    },
    {
        "name": "kokoro_tts",
        "port": 8851,
        "pgrep_pat": "qsb_kokoro_serve.py",
        "launch": [".venv/bin/python3", "tools/qsb_kokoro_serve.py"],
        "log": "logs/qsb_kokoro_serve.log",
    },
    # NOTE: position_monitor is a oneshot tick-task, not a long-running daemon.
    # See tick() step 3a below — it runs the script each cycle without expecting
    # it to stay alive between ticks.
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def is_alive(d) -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", d["pgrep_pat"]],
                            capture_output=True, text=True, timeout=4)
        return r.returncode == 0 and r.stdout.strip() != ""
    except Exception:
        return False


def revive(d):
    Path(d["log"]).parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(d["log"], "a")
    # setsid so the daemon survives the heartbeat's death
    p = subprocess.Popen(d["launch"], cwd=str(ROOT),
                          stdout=log_fh, stderr=log_fh,
                          stdin=subprocess.DEVNULL,
                          start_new_session=True)
    return p.pid


def daemon_sweep():
    """Return list of (daemon_name, state_string)."""
    results = []
    for d in DAEMONS:
        if is_alive(d):
            results.append((d["name"], "alive"))
        else:
            try:
                pid = revive(d)
                results.append((d["name"], f"revived (pid {pid})"))
            except Exception as e:
                results.append((d["name"], f"failed: {str(e)[:80]}"))
    return results


def run_quietly(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                            text=True, timeout=timeout)
        return r.returncode, r.stdout.strip().split("\n")[-1] if r.stdout else ""
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, str(e)[:120]


def detect_boot_event(verbose=True):
    """Compare /proc/stat btime against last-stored value.

    First run: stores btime, no event (state file absence == cold start).
    Subsequent runs with a changed btime: PC was rebooted. Emit a
    boot_event row to qsb_tower_activity_tail.jsonl and stamp F47.

    Per gap audit: makes unplanned reboots machine-detectable.
    """
    state_file = ROOT / "data/registries/qsb_last_boot_time.txt"
    activity_tail = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"
    f47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"

    # read current btime from /proc/stat
    cur_btime = None
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("btime"):
                    cur_btime = int(line.split()[1])
                    break
    except Exception as e:
        if verbose: print(f"  boot_detect: /proc/stat unreadable: {e}")
        return

    if cur_btime is None:
        if verbose: print("  boot_detect: no btime line in /proc/stat")
        return

    # read prior btime
    prev_btime = None
    if state_file.exists():
        try:
            prev_btime = int(state_file.read_text().strip())
        except Exception:
            prev_btime = None

    # first-ever run: just stamp the state file, no event
    if prev_btime is None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(str(cur_btime) + "\n")
        if verbose: print(f"  boot_detect: first run, recorded btime={cur_btime}")
        return

    if prev_btime == cur_btime:
        if verbose: print(f"  boot_detect: no reboot (btime={cur_btime})")
        return

    # changed → PC was rebooted
    gap_min = max(0, (cur_btime - prev_btime) // 60)
    summary = (f"PC rebooted; old_btime={prev_btime}, "
               f"new_btime={cur_btime}, gap_min={gap_min}")
    row = {
        "ts": _now(),
        "event_kind": "boot_event",
        "summary": summary,
    }
    activity_tail.parent.mkdir(parents=True, exist_ok=True)
    with activity_tail.open("a") as f:
        f.write(json.dumps(row) + "\n")

    f47_rec = {
        "ts": _now(),
        "kind": "boot_event",
        "floor": "F47",
        "operator": "heartbeat",
        "executed_by": "Wren+heartbeat",
        "summary": summary,
        "old_btime": prev_btime,
        "new_btime": cur_btime,
        "gap_min": gap_min,
    }
    f47.parent.mkdir(parents=True, exist_ok=True)
    with f47.open("a") as f:
        f.write(json.dumps(f47_rec) + "\n")

    state_file.write_text(str(cur_btime) + "\n")
    if verbose: print(f"  boot_detect: REBOOT detected · {summary}")


# ── leak audit (hourly) ──────────────────────────────────────────────
# Hourly scan of public-facing files for skyscraper internal references.
# Read-only: appends findings to qsb_dashboard_security_audit.jsonl.
# NEVER fixes anything — humans review.
LEAK_AUDIT_INTERVAL_SEC = 60 * 60  # 60 minutes
LEAK_AUDIT_STATE = ROOT / "data/runtime/qsb_leak_audit_last_run.json"
LEAK_AUDIT_LOG   = ROOT / "data/registries/qsb_dashboard_security_audit.jsonl"
LEAK_AUDIT_TARGET = "web/shops/"


def _leak_audit_due(now_epoch: float) -> tuple[bool, float]:
    """Return (due, last_run_epoch). due=True when ≥60 min since last run."""
    try:
        if LEAK_AUDIT_STATE.exists():
            data = json.loads(LEAK_AUDIT_STATE.read_text())
            last = float(data.get("last_run_epoch", 0))
        else:
            last = 0.0
    except Exception:
        last = 0.0
    return (now_epoch - last >= LEAK_AUDIT_INTERVAL_SEC), last


def run_leak_audit_if_due(verbose=True) -> tuple[int, str]:
    """Run tools/qsb_leak_audit.py at most once per 60 min. Read-only.

    Returns (rc, summary). rc=-3 means skipped (not yet due). On run, appends
    one row to data/registries/qsb_dashboard_security_audit.jsonl with
    kind='leak_audit_scan' and a findings summary. NEVER fixes anything.
    """
    now_epoch = time.time()
    due, last = _leak_audit_due(now_epoch)
    if not due:
        mins_left = int((LEAK_AUDIT_INTERVAL_SEC - (now_epoch - last)) / 60)
        return -3, f"skipped (next in ~{mins_left}m)"

    target = ROOT / LEAK_AUDIT_TARGET
    findings: dict = {}
    audit_rc = 0
    audit_err = ""
    try:
        r = subprocess.run(
            ["python3", "tools/qsb_leak_audit.py", str(target), "--json"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        audit_rc = r.returncode
        out = (r.stdout or "").strip()
        if out:
            try:
                findings = json.loads(out)
            except Exception as je:
                audit_err = f"json_parse: {str(je)[:80]}"
        if r.stderr and not audit_err:
            audit_err = r.stderr.strip().split("\n")[-1][:120]
    except subprocess.TimeoutExpired:
        audit_rc = -1
        audit_err = "TIMEOUT"
    except Exception as e:
        audit_rc = -2
        audit_err = str(e)[:120]

    files_with_hits = len(findings) if isinstance(findings, dict) else 0
    total_hits = 0
    if isinstance(findings, dict):
        for hits in findings.values():
            try:
                total_hits += len(hits)
            except Exception:
                pass

    row = {
        "ts": _now(),
        "event": "leak_audit_scan",
        "kind": "leak_audit_scan",
        "tool": "tools/qsb_leak_audit.py",
        "target": LEAK_AUDIT_TARGET,
        "audit_rc": audit_rc,
        "files_with_hits": files_with_hits,
        "total_hits": total_hits,
        "findings": findings,
        "error": audit_err or None,
        "source": "heartbeat",
        "action": "log_only",  # NEVER fix — humans review
    }
    LEAK_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LEAK_AUDIT_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")

    LEAK_AUDIT_STATE.parent.mkdir(parents=True, exist_ok=True)
    LEAK_AUDIT_STATE.write_text(json.dumps({
        "last_run_epoch": now_epoch,
        "last_run_ts": row["ts"],
        "last_audit_rc": audit_rc,
        "last_files_with_hits": files_with_hits,
        "last_total_hits": total_hits,
    }))

    summary = f"ran target={LEAK_AUDIT_TARGET} files={files_with_hits} hits={total_hits}"
    return audit_rc, summary


def tick(verbose=True):
    started_ts = _now()
    if verbose: print(f"\n[heartbeat] tick {started_ts}")

    # 0. boot-event detector (per gap audit) — machine-detect unplanned reboots
    try:
        detect_boot_event(verbose=verbose)
    except Exception as e:
        if verbose: print(f"  boot_detect error: {e}")

    # 1. daemons
    daemons = daemon_sweep()
    if verbose:
        for n, s in daemons:
            print(f"  daemon {n:18s} {s}")

    # 2. mass dispatch (records team task assignments)
    rc, last = run_quietly(["python3", "tools/qsb_mass_dispatch.py"], timeout=60)
    if verbose: print(f"  mass_dispatch rc={rc} · {last[:80]}")

    # 3. position monitor refresh (one-shot, separate from the daemon)
    rc2, last2 = run_quietly(["python3", "-c",
        "from tower.qsb_floor41_oanda import refresh_all; refresh_all()"],
        timeout=20)
    if verbose: print(f"  oanda_refresh rc={rc2}")

    # 3a. OANDA position monitor (TP/SL sweep). One-shot, runs each tick.
    rc_pm, last_pm = run_quietly(["python3", "tools/qsb_oanda_position_monitor.py"],
                                  timeout=30)
    if verbose: print(f"  position_monitor rc={rc_pm} · {last_pm[:60]}")

    # 3a.1. chat_mirror — sync Claude Code session transcripts into tower.
    # 2026-06-26 wired in per team consensus (B>A>C order). Was DORMANT.
    rc_cm, last_cm = run_quietly(["python3", "tools/qsb_chat_mirror.py"], timeout=30)
    if verbose: print(f"  chat_mirror rc={rc_cm} · {last_cm[:60]}")

    # 3a.2. triage brain (qwen3.5:9b) — Ross "wire them all in" 2026-06-26.
    # Reads brief + flags anomalies in last 30 F47 rows. Cadence: per heartbeat
    # tick (default 300s). DeepSeek-signoff wire-in #1.
    rc_tb, last_tb = run_quietly(["python3", "tools/qsb_triage_brain.py", "--quiet"],
                                   timeout=90)
    if verbose: print(f"  triage_brain rc={rc_tb} · {last_tb[:60]}")

    # 3b. F47 graphics research crew — analyzes screenshots, drafts proposals.
    #     Ross 2026-06-13: "your crew can look at it on the web page, they can
    #     start GoDot in a sandbox and check everything... when I come back
    #     from breakfast, I should see progress."
    #     Bounded: max 60 new images per tick (env QSB_PHOTO_LIMIT).
    rc_gx, last_gx = run_quietly(["python3", "tools/qsb_graphics_research_crew.py"],
                                  timeout=120)
    if verbose: print(f"  graphics_crew rc={rc_gx} · {last_gx[:60]}")

    # 3c. Code-proposal multi-sig checker. If a proposal has the required
    #     sigs and CLAUDE.md authorizes auto-apply, apply + audit. Otherwise
    #     just log unsigned proposals for the F47 Ops Console.
    rc_cp, last_cp = run_quietly(["python3", "tools/qsb_code_proposal_checker.py"],
                                  timeout=30)
    if verbose: print(f"  proposal_checker rc={rc_cp} · {last_cp[:60]}")

    # 3d. F47 codebase audit crew — one track per tick (round-robin).
    #     Produces 0-3 proposals from a different angle each cycle.
    rc_ac, last_ac = run_quietly(["python3", "tools/qsb_codebase_audit_run.py"],
                                  timeout=60)
    if verbose: print(f"  audit_crew rc={rc_ac} · {last_ac[:60]}")

    # 3e. Auto-sigs loop — sandbox each new proposal + add wren_crew +
    #     team_assistants sigs when criteria met. Conservative allow-list.
    rc_as, last_as = run_quietly(["python3", "tools/qsb_auto_sigs.py"],
                                  timeout=60)
    if verbose: print(f"  auto_sigs rc={rc_as} · {last_as[:60]}")

    # 3f. Applier — turns 3-sig + green-sandbox proposals into actual file
    #     mutations. Refuses safety paths. Writes audit row for every apply.
    rc_ap, last_ap = run_quietly(["python3", "tools/qsb_proposal_applier.py"],
                                  timeout=60)
    if verbose: print(f"  applier rc={rc_ap} · {last_ap[:60]}")

    # 3g. Chat mirror — copy new user+assistant turns from Claude Code
    #     transcripts into tower-owned qsb_chat_log.jsonl. High-water-mark
    #     tracked per session so each tick is incremental.
    rc_cm, last_cm = run_quietly(["python3", "tools/qsb_chat_mirror.py", "mirror"],
                                  timeout=30)
    if verbose: print(f"  chat_mirror rc={rc_cm} · {last_cm[:60]}")

    # 3h. Buffer snapshot — atomic capture of all volatile state every tick.
    #     Survives crashes/reboots; archives last 12 so a corrupted current
    #     can roll back to last-known-good. Ross 2026-06-14: "100% persistent".
    rc_bs, last_bs = run_quietly(["python3", "tools/qsb_buffer_snapshot.py"],
                                  timeout=15)
    if verbose: print(f"  buffer_snapshot rc={rc_bs} · {last_bs[:60]}")

    # 3i. Wake briefing — synth markdown briefing read by next-Wren on wake.
    #     Reads buffer + diary + decisions + letters + dead-ideas catalogue.
    #     Cheap to regenerate every tick so it's always current.
    rc_wb, last_wb = run_quietly(["python3", "tools/qsb_wake_briefing.py"],
                                  timeout=15)
    if verbose: print(f"  wake_briefing rc={rc_wb} · {last_wb[:60]}")

    # 3j. Supervisor — escalates if a daemon needs revival >3x in 60 min.
    #     Observer only, no autonomous worker dispatch.
    rc_sv, last_sv = run_quietly(["python3", "tools/qsb_supervisor.py"],
                                  timeout=15)
    if verbose: print(f"  supervisor rc={rc_sv} · {last_sv[:60]}")

    # 3k. Leak audit — hourly scan of public-facing web/shops/ for skyscraper
    #     internal references. Gated by a last-run timestamp file so it only
    #     fires once per 60 min regardless of tick interval. NEVER fixes
    #     anything — append-only log to qsb_dashboard_security_audit.jsonl;
    #     humans review.
    try:
        rc_la, last_la = run_leak_audit_if_due(verbose=verbose)
        if verbose: print(f"  leak_audit rc={rc_la} · {last_la[:60]}")
    except Exception as e:
        if verbose: print(f"  leak_audit error: {e}")

    # 3l. Timeclock shift-status — wires orphan tools/qsb_timeclock.py into the
    #     heartbeat. Stamps a visitor-safe snapshot of who's clocked-in this
    #     hour, bucketed by floor category. NO operative PII — just counts.
    #     Appends to data/registries/qsb_timeclock_audit.jsonl.
    rc_tc = -99
    last_tc = ""
    try:
        if str(ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(ROOT / "tools"))
        import qsb_timeclock as _tc
        snap = _tc.status()
        buckets: dict[str, int] = {}
        for entry in snap.get("on_shift", []):
            floor = entry.get("floor")
            key = f"F{floor}" if floor is not None else "unassigned"
            buckets[key] = buckets.get(key, 0) + 1
        audit_row = {
            "ts": _now(),
            "kind": "shift_status",
            "on_shift_count": snap.get("on_shift_count", 0),
            "off_shift_count": snap.get("off_shift_count", 0),
            "by_floor": buckets,
        }
        audit_path = ROOT / "data/registries/qsb_timeclock_audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a") as f:
            f.write(json.dumps(audit_row) + "\n")
        rc_tc = 0
        last_tc = f"on={audit_row['on_shift_count']} off={audit_row['off_shift_count']}"
    except Exception as e:
        last_tc = str(e)[:60]
    if verbose: print(f"  timeclock_audit rc={rc_tc} · {last_tc[:60]}")

    # 3y. /tmp snapshot — /tmp is wiped on reboot but holds runner scripts +
    #     logs we don't want to lose (qwen download runner, dashboard log,
    #     screenshots). Calls into qsb_pitstop's snapshot_tmp_files() with a
    #     rolling "heartbeat" timestamp so old snapshots get overwritten by
    #     newer ones and the disk doesn't bloat. Ross 2026-06-20: "we need
    #     a way to save our temp files as well".
    rc_ts = -99
    last_ts = ""
    try:
        if str(ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(ROOT / "tools"))
        import qsb_pitstop as _ps
        # Use a single rolling slot so heartbeat doesn't bloat disk — keeps
        # the latest snapshot only. Manual pitstop still creates per-ts dirs.
        snap = _ps.snapshot_tmp_files("heartbeat_rolling", [])
        rc_ts = 0
        last_ts = f"copied={snap.get('copied_count', 0)} → {snap.get('snapshot_dir', '?')}"
    except Exception as e:
        last_ts = str(e)[:80]
    if verbose: print(f"  tmp_snapshot rc={rc_ts} · {last_ts[:80]}")

    # 3z. wren team day-shift dispatch — pip/forge/mira/bram/cass each get
    #     one short read-only task during work hours. Skipped outside 8-17.
    rc_wt, last_wt = run_quietly(
        ["python3", "tools/qsb_wren_team_dispatch.py"], timeout=360)
    if verbose: print(f"  wren_team rc={rc_wt} · {last_wt[:80]}")

    # 4. steward briefing snapshot
    rc3, last3 = run_quietly(["python3", "tools/qsb_wren_steward_briefing.py",
                                "--json"], timeout=15)
    if verbose: print(f"  steward_briefing rc={rc3}")

    # 5. stamp F47
    rec = {
        "ts": _now(),
        "kind": "heartbeat_tick",
        "floor": "F47",
        "operator": "background",
        "executed_by": "Wren+heartbeat",
        "daemons": [{"name": n, "state": s} for n, s in daemons],
        "mass_dispatch_rc": rc,
        "oanda_refresh_rc": rc2,
        "steward_briefing_rc": rc3,
    }
    f47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
    with f47.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    if verbose: print(f"  F47 stamped at {rec['ts']}")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=300,
                    help="seconds between ticks (default 300 = 5 min)")
    ap.add_argument("--once", action="store_true",
                    help="run a single tick and exit")
    args = ap.parse_args()

    # Reaper-friendly: SIGTERM ends gracefully
    stopping = {"flag": False}
    def _term(*_):
        stopping["flag"] = True
        print("[heartbeat] stopping on signal")
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    print(f"[heartbeat] tower runtime starting at {_now()}")
    print(f"  interval: {args.interval}s")
    if args.once:
        tick(verbose=True)
        return

    while not stopping["flag"]:
        try:
            tick(verbose=True)
        except Exception as e:
            print(f"[heartbeat] tick error: {e}")
        # Sleep in 1s steps so we react to SIGTERM
        for _ in range(args.interval):
            if stopping["flag"]: break
            time.sleep(1)
    print(f"[heartbeat] tower runtime stopped at {_now()}")


if __name__ == "__main__":
    main()
