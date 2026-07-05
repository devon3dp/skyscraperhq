"""qsb_trader_manager.py — live AI supervisor over the trader fleet.

Per Ross 2026-06-24 "we need an active AI that looks over all traders and looks for bleeds".

Architecture: HYBRID (3-of-3 panel: Hermes+OpenAI+DeepSeek unanimous on option C).

FAST PATH (event-driven):
- Subscribes to trade.closed on the bus
- Maintains rolling buffer of last 5 trades per worker
- INSTANT PAUSE if trailing 3-trade PnL < -£5 OR 2 consecutive REAL losses
- Pause = kill the worker process + record in qsb_paused_workers.json

SLOW PATH (every 300s):
- For each paused worker, check recent_pnl + recent_wr
- Auto-resume if 3 consecutive wins in their tail OR pnl recovering
- (qwen2.5:32b judgment layer deferred to v2 — rule-based first per principle of
  "simple solutions before AI")

HEARTBEAT:
- Every 60s emits trader_manager.health event to bus with current state
- Records to data/registries/qsb_trader_manager_state.json

ACTIONS:
- pause(worker_id, reason) → kill process, mark paused with timestamp + reason
- resume(worker_id) → respawn process from roster, clear pause flag
- All actions logged to F47.
"""
from __future__ import annotations
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

# Bus subscriber (same as belief_updater pattern)
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402

PAUSED_FILE = ROOT / "data/registries/qsb_paused_workers.json"
STATE_FILE = ROOT / "data/registries/qsb_trader_manager_state.json"
F47_FILE = ROOT / "data/registries/qsb_f47_team_records.jsonl"
ROSTER_FILE = ROOT / "data/registries/qsb_belief_workers.json"

# Thresholds (DeepSeek recommended + Claude refinement after first-spin false-pause)
TRAILING_WINDOW = 5
PAUSE_PNL_THRESHOLD = -5.0      # 3-trade pnl sum < -£5 → pause
PAUSE_LOSS_STREAK = 3           # 3 consecutive REAL losses (was 2 — micro-losses triggered)
MIN_LOSS_MAGNITUDE = 0.10       # any loss in streak must be > £0.10 to count
RESUME_WIN_STREAK = 3           # 3 consecutive wins → resume eligible
SLOW_PATH_INTERVAL = 300        # 5-min auto-resume review
HEARTBEAT_INTERVAL = 60         # 60s state publish


def now_utc_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_paused() -> dict:
    if PAUSED_FILE.exists():
        try:
            return json.loads(PAUSED_FILE.read_text())
        except Exception:
            pass
    return {}


def save_paused(d: dict) -> None:
    PAUSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAUSED_FILE.write_text(json.dumps(d, indent=2))


def stamp_f47(kind: str, subject: str, detail: str, **extra) -> None:
    row = {"ts": now_utc_iso(), "kind": kind, "role": "trader_manager",
           "subject": subject, "detail": detail, **extra}
    with F47_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")


def kill_worker_process(worker_id: str) -> int:
    """Kill any process with --worker-id <name>. Returns count killed."""
    killed = 0
    # Use pgrep -af with -- to terminate option parsing, AND match worker_id pattern
    try:
        out = subprocess.check_output(["pgrep", "-af", worker_id]).decode().splitlines()
        for line in out:
            parts = line.split(None, 1)
            if len(parts) < 2 or worker_id not in parts[1]:
                continue
            # Ensure it's a trader process, not another tool
            if "qsb_belief_driven_trader" not in parts[1]:
                continue
            try:
                os.kill(int(parts[0]), signal.SIGKILL)
                killed += 1
            except Exception:
                pass
    except subprocess.CalledProcessError:
        pass
    return killed


def spawn_worker_from_roster(worker_id: str) -> bool:
    """Re-spawn a paused worker using its roster entry."""
    try:
        roster = json.loads(ROSTER_FILE.read_text())
    except Exception:
        return False
    cfg = roster.get(worker_id)
    if not cfg:
        return False
    venue = cfg.get("venue")
    instruments = cfg.get("instruments") or []
    if not (venue and instruments):
        return False
    inst = instruments[0]
    # Strategy from worker_id suffix
    strat = "baseline"
    for suf in ("_momentum", "_meanrevert", "_breakout", "_ta"):
        if worker_id.endswith(suf):
            strat = suf[1:] if suf != "_ta" else "ta_classic"
    # Sim units per venue (matches current fleet)
    sim = "0.01" if venue == "binance" else "500"
    short = worker_id.replace("belief_driven_", "")
    log = ROOT / f"logs/intelligence/trader_{short}.log"
    cmd = ["python3", "tools/qsb_belief_driven_trader.py",
           "--worker-id", worker_id, "--venue", venue, "--instrument", inst,
           "--strategy", strat, "--sim-units", sim]
    try:
        with log.open("a") as f:
            f.write(f"\n[trader_manager resume {now_utc_iso()}]\n")
            subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT,
                             cwd=str(ROOT), start_new_session=True)
        return True
    except Exception:
        return False


class TraderManager:
    def __init__(self):
        self.sub = QSBSubscriber("trader_manager")
        # rolling per-worker: deque[(pnl, won, ts)]
        self.recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=TRAILING_WINDOW))
        self.last_heartbeat = 0.0
        self.last_slow_path = 0.0

    async def on_trade_closed(self, event: dict) -> None:
        payload = event.get("payload", {})
        wid = payload.get("worker_id")
        pnl = payload.get("pnl")
        won = payload.get("won")
        is_real = payload.get("is_real", True)
        if not (wid and pnl is not None and won is not None):
            return
        if not is_real:
            return  # ignore SIM closes (Ross "no sims")
        self.recent[wid].append((float(pnl), bool(won), time.time()))
        # FAST PATH check
        paused = load_paused()
        if wid in paused and paused[wid].get("paused"):
            return  # already paused
        trades = list(self.recent[wid])
        if len(trades) >= 3:
            recent3_pnl = sum(t[0] for t in trades[-3:])
            if recent3_pnl < PAUSE_PNL_THRESHOLD:
                self.pause(wid, f"trailing_3_pnl={recent3_pnl:.2f}<{PAUSE_PNL_THRESHOLD}")
                return
        # Consecutive REAL losses — only count losses with magnitude > MIN_LOSS_MAGNITUDE
        tail = trades[-PAUSE_LOSS_STREAK:]
        if len(tail) >= PAUSE_LOSS_STREAK and all(not t[1] for t in tail):
            if all(t[0] < -MIN_LOSS_MAGNITUDE for t in tail):
                losses_sum = sum(t[0] for t in tail)
                self.pause(wid, f"loss_streak_{PAUSE_LOSS_STREAK}_sum={losses_sum:.2f}")

    def pause(self, worker_id: str, reason: str) -> None:
        killed = kill_worker_process(worker_id)
        paused = load_paused()
        paused[worker_id] = {"paused": True, "paused_at": now_utc_iso(),
                              "reason": reason, "killed_procs": killed}
        save_paused(paused)
        print(f"[manager] PAUSED {worker_id} — {reason} (killed {killed} procs)", flush=True)
        stamp_f47("trader_manager_pause",
                  f"AUTO PAUSE {worker_id}",
                  f"Reason: {reason}. Killed {killed} processes.",
                  worker_id=worker_id, reason=reason)

    def resume(self, worker_id: str) -> None:
        ok = spawn_worker_from_roster(worker_id)
        paused = load_paused()
        if worker_id in paused:
            del paused[worker_id]
        save_paused(paused)
        print(f"[manager] RESUMED {worker_id} (spawn ok={ok})", flush=True)
        stamp_f47("trader_manager_resume",
                  f"AUTO RESUME {worker_id}",
                  f"Spawn ok={ok}.",
                  worker_id=worker_id)
        self.recent[worker_id].clear()  # fresh start

    async def slow_path_review(self) -> None:
        """Every 300s: review paused workers, resume if they look healthy."""
        paused = load_paused()
        for wid, info in list(paused.items()):
            if not info.get("paused"):
                continue
            recent = list(self.recent.get(wid, []))
            # Conservative: need RESUME_WIN_STREAK consecutive wins
            tail = recent[-RESUME_WIN_STREAK:]
            if len(tail) >= RESUME_WIN_STREAK and all(t[1] for t in tail):
                self.resume(wid)

    async def heartbeat(self) -> None:
        paused = load_paused()
        state = {
            "ts": now_utc_iso(),
            "paused": {wid: info for wid, info in paused.items() if info.get("paused")},
            "active_workers": {wid: {"n_recent": len(self.recent[wid]),
                                       "recent_pnl": sum(t[0] for t in self.recent[wid])}
                                for wid in self.recent if wid not in paused},
        }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
        await self.sub.publish("trader_manager.health", state)

    async def loop_supervisor(self) -> None:
        """Heartbeat + slow-path on an interval. Pure event-loop, no clocks in trading logic."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await self.heartbeat()
            now = time.time()
            if now - self.last_slow_path >= SLOW_PATH_INTERVAL:
                self.last_slow_path = now
                await self.slow_path_review()

    async def run(self) -> None:
        self.sub.on("trade.closed", self.on_trade_closed)
        # Run subscriber + supervisor concurrently
        await asyncio.gather(
            self.sub.run(subscriptions=["trade.closed"]),
            self.loop_supervisor(),
        )


if __name__ == "__main__":
    print(f"[trader_manager] starting; "
          f"fast={PAUSE_PNL_THRESHOLD}/£3-trades or {PAUSE_LOSS_STREAK}-loss-streak | "
          f"slow={SLOW_PATH_INTERVAL}s | heartbeat={HEARTBEAT_INTERVAL}s",
          flush=True)
    mgr = TraderManager()
    asyncio.run(mgr.run())
