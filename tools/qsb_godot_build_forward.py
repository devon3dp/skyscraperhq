#!/usr/bin/env python3
"""qsb_godot_build_forward.py — autonomous Godot v2 build progress.

Runs from a systemd-user timer (every 12 min). Picks one item off a
backlog, dispatches a provider agent (Otto/Dex) to draft the work,
stamps F47, queues the result for Claude review on next wake.

This is the "build keeps moving when Ross isn't in the CLI" mechanism.

Bounds (per CLAUDE.md):
- still NOT autonomous tower execution — only PROPOSALS get drafted
- still NOT heartbeat-triggered (different cadence, different unit)
- Wren-initiated equivalence is okay; tick stamps an audit row

Backlog file: data/registries/qsb_godot_v2_backlog.jsonl
Status writes: F47 + qsb_godot_build_forward_log.jsonl
"""
from __future__ import annotations
import datetime, json, os, pathlib, random, subprocess, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
BACKLOG = REG / "qsb_godot_v2_backlog.jsonl"
LOG = REG / "qsb_godot_build_forward_log.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
PROVIDER_AGENT = ROOT / "tools/qsb_provider_agent.py"


SEED_BACKLOG = [
    {"id":"v2_b1", "kind":"hud", "title":"add live worker count to TOWER STATS panel from bus snapshot.workers field",
     "delegate":"dex", "agent_task":"Look at Main_v2.gd _refresh_hud — bus.snapshot() returns a dict. Find where 'workers' lives in the response (use grep on src/dashboard for native_cockpit/state JSON). Propose a wren_edit_file patch to Main_v2.gd that pulls workers_total = snap.get('workers',[]).size() and renders it. Stamp F47 with the patch."},
    {"id":"v2_b2", "kind":"feature", "title":"wire FloorClickRouter signal so clicking a floor opens interior",
     "delegate":"dex", "agent_task":"Read scripts/v2/Main_v2.gd. _on_enter_interior already exists but is a stub. Propose a wren_edit_file patch that: hides tower group, instances FloorInteriorController on enter, restores tower on leave. Stamp F47 with the patch as a multi-line string."},
    {"id":"v2_b3", "kind":"interaction", "title":"add G key to enter walk mode using WalkableFloorMode.enter_walk",
     "delegate":"otto", "agent_task":"Read scripts/WalkableFloorMode.gd. Find enter_walk + leave_walk signatures. Propose the 5-line patch for Main_v2.gd _input to toggle walk mode on G. Stamp F47."},
    {"id":"v2_b4", "kind":"polish", "title":"selected-floor camera focus animation smoother (lerp speed)",
     "delegate":"otto", "agent_task":"Read scripts/CameraController.gd focus_on_floor — what's the lerp speed? Propose a Main_v2.gd line that tunes camera_controller smoothing. Stamp F47."},
    {"id":"v2_b5", "kind":"dashboard", "title":"draft FastAPI dashboard_v2 floors route",
     "delegate":"dex", "agent_task":"Draft src/dashboard_v2/routes/floors.py — FastAPI router with GET /v2/floors returning [{idx, name, department, status, worker_count}] read from data/registries/qsb_floor*_card.json. Stamp F47 with the Python code."},
    {"id":"v2_b6", "kind":"qa", "title":"smoke test Main_v2.tscn headless",
     "delegate":"smoke", "agent_task":"local smoke — no provider"},
    {"id":"v2_b7", "kind":"hud", "title":"add bus connection health indicator (green dot / red dot)",
     "delegate":"otto", "agent_task":"Propose a Main_v2 patch that adds a small icon/Label in TopBar showing green when bus.is_connected_ok() else red. Stamp F47 with the patch."},
    {"id":"v2_b8", "kind":"interaction", "title":"add Tab to cycle selected floor",
     "delegate":"otto", "agent_task":"Propose Main_v2 patch: on Tab key, increment selected_floor; on Shift+Tab, decrement. Wrap 1..165. Call _on_floor_selected with the new idx. Stamp F47."},
    {"id":"v2_b9", "kind":"feature", "title":"wire TowerLiftSystem to bus.lifts data so they animate based on telemetry",
     "delegate":"dex", "agent_task":"Read TowerLiftSystem.gd — find a public method that accepts lift state. Propose a Main_v2 _on_bus_snapshot patch that forwards snap['lifts'] to lift_system. Stamp F47."},
    {"id":"v2_b10", "kind":"polish", "title":"add subtle vignette + glow to camera (cockpit feel)",
     "delegate":"otto", "agent_task":"Propose CameraAttributesPractical settings to add to Main_v2's Camera3D for slight DoF + vignette. Stamp F47 patch."},
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def _init_backlog_if_empty() -> list[dict]:
    if BACKLOG.exists():
        return [json.loads(l) for l in BACKLOG.read_text().splitlines() if l.strip()]
    BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for it in SEED_BACKLOG:
        row = {**it, "ts_added": now_iso(), "status": "pending", "ts_started": None, "ts_done": None}
        rows.append(row)
    BACKLOG.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return rows


def _save_backlog(rows: list[dict]):
    BACKLOG.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _stamp(kind: str, summary: str):
    with F47.open("a") as f:
        f.write(json.dumps({"ts": now_iso(), "kind": kind, "operator":"build_forward", "summary": summary[:500]})+"\n")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"ts": now_iso(), "kind": kind, "summary": summary[:500]})+"\n")


def dispatch_via_provider(item: dict) -> dict:
    """Spawn an Otto/Dex run for this backlog item. Returns dict with result."""
    provider = "openai" if item["delegate"] == "otto" else "deepseek"
    model = "gpt-4o-mini" if provider == "openai" else "deepseek-chat"
    sys_prompt = f"You are {'Otto' if provider=='openai' else 'Dex'}. STAMP F47 in 6 turns max. Builder voice. Working on Godot v2 backlog item id={item['id']}."
    task = item["agent_task"]
    log_path = f"/tmp/bf_{item['id']}.log"
    cmd = [
        "python3", str(PROVIDER_AGENT),
        "--provider", provider, "--model", model,
        "--system", sys_prompt, "--task", task,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        with open(log_path, "w") as f: f.write(r.stdout + "\n[stderr]\n" + r.stderr)
        return {"ok": r.returncode == 0, "log": log_path, "stdout_tail": r.stdout[-400:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "log": log_path, "stdout_tail": "timeout"}
    except Exception as e:
        return {"ok": False, "log": log_path, "stdout_tail": str(e)[:200]}


def run_smoke() -> dict:
    """Local smoke — run headless Godot v2 and check for parse errors."""
    log = "/tmp/bf_smoke.log"
    cmd = [
        "timeout", "12",
        "/snap/godot-4/21/godot-4", "--headless",
        "--path", "/home/ross/qsb_godot_native_cockpit",
        "--quit-after", "4",
        "res://scenes/Main_v2.tscn",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    open(log, "w").write(r.stdout + "\n[stderr]\n" + r.stderr)
    errs = sum(1 for line in (r.stdout + r.stderr).splitlines() if any(x in line for x in ("SCRIPT ERROR","Parse Error","Invalid call")))
    return {"ok": errs == 0, "log": log, "errors": errs}


def main():
    """Each tick: take up to 3 pending items in parallel. Multi-agent."""
    rows = _init_backlog_if_empty()
    pending = [r for r in rows if r["status"] == "pending"]
    if not pending:
        _stamp("build_forward_idle", "backlog drained — no pending items")
        print("backlog drained"); return
    # Multi-agent — scale by hardware headroom (CPU/GPU/RAM/temps)
    batch_size = 3
    hw_log = REG / "qsb_hw_stats.jsonl"
    if hw_log.exists():
        try:
            with hw_log.open() as f:
                last = None
                for line in f: last = line
            if last:
                last_sample = json.loads(last)
                rec = last_sample.get("headroom", {}).get("parallel_agents_recommended", 3)
                batch_size = max(1, min(int(rec), len(pending)))
        except Exception:
            pass
    batch = pending[:batch_size]
    for item in batch:
        item["status"] = "in_progress"
        item["ts_started"] = now_iso()
    _save_backlog(rows)
    _stamp("build_forward_tick", f"batch of {len(batch)}: " + ", ".join(it["id"] for it in batch))

    # Fire them in parallel via subprocess.Popen, then collect.
    import threading
    results = {}
    def _worker(it):
        if it["delegate"] == "smoke":
            results[it["id"]] = run_smoke()
        else:
            results[it["id"]] = dispatch_via_provider(it)
    threads = [threading.Thread(target=_worker, args=(it,)) for it in batch]
    for t in threads: t.start()
    for t in threads: t.join()

    for it in batch:
        r = results.get(it["id"], {"ok": False, "stdout_tail":"no result"})
        it["status"] = "done" if r.get("ok") else "blocked"
        it["ts_done"] = now_iso()
        it["result"] = r
        _stamp(
            "build_forward_done" if r.get("ok") else "build_forward_blocked",
            f"{it['id']} ({it['delegate']}) → {it['status']}: tail={r.get('stdout_tail','')[:140]}"
        )
        print(f"{it['id']} → {it['status']}")
    _save_backlog(rows)

if __name__ == "__main__":
    main()
