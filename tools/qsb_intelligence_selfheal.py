#!/usr/bin/env python3
"""
qsb_intelligence_selfheal.py — self-healing watchdog for the QSB intelligence / streams layer.

Sibling to tools/qsb_underground_selfheal.py (the proven map self-healer), applying the same
discipline to the trading-intelligence pipeline: the F41/F42/F43 tick streams, the
belief_updater daemon, and the regime_detector. These run LOOSE under cron (@reboot +
5-min via deploy/qsb_tower_boot.sh -> scripts/spawn_streams_layer.sh). The cron spawner
only checks PROCESS EXISTENCE (`is_alive`) — it CANNOT detect a SILENT STALL (a process
that is alive but no longer producing: bus disconnected, stream socket wedged, updater
hung). That is exactly the map's stale-render bug class, applied to the traders' brain.

This watchdog detects + heals the REAL stall modes by DATA FRESHNESS, not process existence:

  1. TICK STREAM STALLED  -> a venue's tick stream file (qsb_<venue>_tick_stream.jsonl) has
     not grown in > threshold. Heal by re-running the idempotent spawn_streams_layer.sh,
     which restarts ONLY the dead/stalled tools (it skips ones still alive). We first kill
     the stalled-but-alive process so the spawner re-launches it.
  2. BELIEF UPDATER STALLED -> the traders' intelligence source. Its real heartbeat is the
     newest data/registries/cognitive/belief_state_*.json mtime (written on every mutation;
     the stdout log file mtime is unreliable due to Python buffering). If no belief_state
     has changed in > threshold WHILE at least one tick stream is fresh (so evidence IS
     flowing and beliefs SHOULD be updating), the updater is stalled -> kill + respawn.
  3. COMPONENT MISSING -> a tool not running at all -> spawn_streams_layer.sh brings it back.

Honesty (R01): every check is a real filesystem/process probe. Every heal writes a row to
data/registries/qsb_intelligence_selfheal.jsonl. If nothing needs healing it logs "ok".
NO execution gates are touched — this only self-restarts EXISTING already-authorized local
services. It does NOT touch the map, Wren/Bill minds, or any SAFETY_DENY path.

Runs as the ross user (systemd --user or system unit as ross) so it can spawn the same
loose tools the cron path spawns. Restart is done by killing the stalled PID + re-running
spawn_streams_layer.sh (which is what the whole tower already trusts for this layer).
"""
import json, os, signal, subprocess, time, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SPAWN = ROOT / "scripts" / "spawn_streams_layer.sh"
BELIEF_DIR = ROOT / "data" / "registries" / "cognitive"
LOG = ROOT / "data" / "registries" / "qsb_intelligence_selfheal.jsonl"

# venue tool -> its freshness-signal file (the data it produces)
STREAMS = {
    "qsb_f41_oanda_stream.py":  ROOT / "data" / "registries" / "qsb_oanda_tick_stream.jsonl",
    "qsb_f42_binance_stream.py": ROOT / "data" / "registries" / "qsb_binance_tick_stream.jsonl",
    "qsb_f43_alpaca_stream.py": ROOT / "data" / "registries" / "qsb_alpaca_tick_stream.jsonl",
}
BELIEF_TOOL = "qsb_belief_updater.py"

# Thresholds. Generous to avoid false restarts across weekend/market gaps.
# Binance (crypto) trades 24/7, so at least one tick stream + beliefs should stay fresh
# around the clock; we treat a stall only when data that SHOULD be flowing has gone quiet.
STREAM_STALE_S = 600   # 10 min with no new ticks on a venue = that venue's stream is wedged
BELIEF_STALE_S = 900   # 15 min with no belief mutation while ticks ARE flowing = updater hung


def _log(action, reason, detail=""):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "action": action, "reason": reason, "detail": str(detail)[:200]}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    print(f"[intel-selfheal] {action} :: {reason} {detail}", flush=True)


def _mtime(p):
    try:
        return p.stat().st_mtime
    except Exception:
        return 0


def _newest_belief_mtime():
    newest = 0
    try:
        for p in BELIEF_DIR.glob("belief_state_*.json"):
            m = p.stat().st_mtime
            if m > newest:
                newest = m
    except Exception:
        pass
    return newest


def _pids_for(tool):
    """PIDs of running python processes whose cmdline contains the tool filename.
    Uses ps + substring match (same technique the tower's spawn scripts use) to avoid
    pgrep self-matching. Excludes THIS watchdog's own process."""
    out = subprocess.run(["ps", "-eo", "pid,cmd", "ww"], capture_output=True, text=True).stdout
    me = os.getpid()
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_s, cmd = line.split(None, 1)
            pid = int(pid_s)
        except ValueError:
            continue
        if pid == me:
            continue
        if "python" in cmd and tool in cmd and "selfheal" not in cmd:
            pids.append(pid)
    return pids


def _kill(pids, reason):
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    # give it a moment, then SIGKILL any survivor
    time.sleep(2)
    for pid in pids:
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def _respawn():
    """Run the idempotent streams spawner. It (re)starts ONLY tools that are not alive,
    so after we've killed a stalled process this brings exactly it back."""
    r = subprocess.run(["bash", str(SPAWN)], capture_output=True, text=True, timeout=60)
    return (r.stdout or "").strip().splitlines()[-1:] or [""]


def main():
    healed = []
    now = time.time()
    respawn_needed = False

    # ── Check per-venue tick streams: stalled (alive but no new ticks) or missing ──
    for tool, feed in STREAMS.items():
        pids = _pids_for(tool)
        age = now - _mtime(feed)
        if not pids:
            _log("component_missing", f"{tool} not running", f"feed_age={int(age)}s")
            respawn_needed = True
            healed.append("missing:" + tool)
        elif age > STREAM_STALE_S:
            _log("stream_stalled", f"{tool} alive but feed stale", f"feed_age={int(age)}s pids={pids}")
            _kill(pids, "stalled stream")
            respawn_needed = True
            healed.append("stalled:" + tool)

    # ── Check belief_updater: stalled iff ticks ARE flowing but beliefs are NOT updating ──
    freshest_stream_age = min((now - _mtime(f)) for f in STREAMS.values())
    belief_age = now - _newest_belief_mtime()
    bu_pids = _pids_for(BELIEF_TOOL)
    if not bu_pids:
        _log("component_missing", "belief_updater not running", f"belief_age={int(belief_age)}s")
        respawn_needed = True
        healed.append("missing:" + BELIEF_TOOL)
    elif belief_age > BELIEF_STALE_S and freshest_stream_age < STREAM_STALE_S:
        # evidence is flowing (a stream is fresh) yet no belief has mutated -> updater hung
        _log("belief_updater_stalled", "ticks fresh but no belief mutation",
             f"belief_age={int(belief_age)}s stream_age={int(freshest_stream_age)}s pids={bu_pids}")
        _kill(bu_pids, "stalled belief_updater")
        respawn_needed = True
        healed.append("stalled:" + BELIEF_TOOL)

    if respawn_needed:
        tail = _respawn()
        _log("respawned", "ran spawn_streams_layer.sh", " ".join(tail))

    if not healed:
        _log("ok", "all healthy",
             f"belief_age={int(belief_age)}s freshest_stream_age={int(freshest_stream_age)}s")

    print(json.dumps({"healed": healed}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
