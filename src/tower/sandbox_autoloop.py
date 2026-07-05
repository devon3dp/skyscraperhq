#!/usr/bin/env python3
"""
QSB Tower V1.3 — Sandbox AutoLoop V1

Background loop for safe paper-only tower motion.

Each cycle:
1. Runs SandboxPerformanceLoop for one paper-only tick.
2. Updates Worker Sandbox / Floor 41 ledger through the performance loop.
3. Runs OpenClaw sandbox visual tick.
4. Writes heartbeat/status for dashboard visibility.

No live orders.
No practice orders.
No real OpenClaw execution.
No real worker execution.
No autonomous dispatch.
"""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import time
import traceback

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/sandbox_autoloop.jsonl"

STOP_FILE = RUNTIME / "sandbox_autoloop.stop"
STATE_FILE = RUNTIME / "sandbox_autoloop_state.json"
LATEST_FILE = REG / "sandbox_autoloop_latest.json"

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
}


def load_local_env_file():
    env = ROOT / ".env.oanda_practice"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("export "):
            continue
        k, _, v = line.replace("export ", "", 1).partition("=")
        if k:
            os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_jsonl(path, record):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def policy():
    return load_json(REG / "sandbox_autoloop_policy.json", {})


def compact_summary(perf_report, openclaw_report, cycle_index):
    perf = perf_report.get("performance", {}) if isinstance(perf_report, dict) else {}
    worker_latest = load_json(REG / "worker_sandbox_latest_tick.json", {})
    ledger = load_json(REG / "floor41_paper_ledger.json", {})
    openclaw_latest = load_json(REG / "openclaw_sandbox_latest.json", {})

    return {
        "ts": now(),
        "phase": "SANDBOX_AUTOLOOP_V1",
        "status": "running",
        "cycle_index": cycle_index,
        "mode": "paper_only_background_loop",
        "ticks_completed": perf_report.get("ticks_completed") if isinstance(perf_report, dict) else None,
        "performance": {
            "entries_analyzed": perf.get("entries_analyzed"),
            "total_paper_score": perf.get("total_paper_score"),
            "total_observation_delta_pips": perf.get("total_observation_delta_pips"),
            "by_instrument": perf.get("by_instrument", [])
        },
        "worker_sandbox": {
            "latest_tick_ts": worker_latest.get("ts"),
            "latest_packet_count": len(worker_latest.get("lift_packets", [])),
            "worker_execution_enabled": False
        },
        "ledger": {
            "entry_count": ledger.get("entry_count", 0),
            "latest_entry_count": ledger.get("latest_entry_count", 0)
        },
        "openclaw_sandbox": {
            "latest_ts": openclaw_latest.get("ts"),
            "packet_count": len(openclaw_latest.get("packets", [])),
            "recommendations": openclaw_latest.get("recommendations", []),
            "openclaw_execution_enabled": False
        },
        "locks": LOCKS,
        "paper_only": True,
        "not_financial_advice": True
    }


class SandboxAutoLoop:
    def __init__(self):
        load_local_env_file()
        self.policy = policy()

    def tick_once(self, cycle_index=1, instruments=None, kernel_commentary=False):
        if instruments is None:
            instruments = self.policy.get("default_instruments", "EUR_USD,GBP_USD,USD_JPY")

        started = now()

        from tower.sandbox_performance_loop import SandboxPerformanceLoop
        from tower.openclaw_sandbox_layer import OpenClawSandboxLayer

        perf_report = SandboxPerformanceLoop().run(
            ticks=1,
            delay_seconds=0,
            instruments=instruments,
            kernel_commentary=kernel_commentary
        )

        openclaw_report = OpenClawSandboxLayer().tick()

        summary = compact_summary(perf_report, openclaw_report, cycle_index)
        summary["started_ts"] = started
        summary["completed_ts"] = now()
        summary["kernel_commentary_requested"] = bool(kernel_commentary)

        write_json(LATEST_FILE, summary)
        write_json(STATE_FILE, summary)
        append_jsonl(LOG, summary)

        return summary

    def loop(self, interval_seconds=30, instruments=None, kernel_every=5, max_ticks=0):
        STOP_FILE.unlink(missing_ok=True)

        cycle = 0
        state = {
            "ts": now(),
            "phase": "SANDBOX_AUTOLOOP_V1",
            "status": "starting",
            "interval_seconds": interval_seconds,
            "max_ticks": max_ticks,
            "locks": LOCKS,
            "paper_only": True
        }
        write_json(STATE_FILE, state)
        write_json(LATEST_FILE, state)

        while True:
            if STOP_FILE.exists():
                stopped = {
                    "ts": now(),
                    "phase": "SANDBOX_AUTOLOOP_V1",
                    "status": "stopped_by_request",
                    "cycle_index": cycle,
                    "locks": LOCKS,
                    "paper_only": True
                }
                write_json(STATE_FILE, stopped)
                write_json(LATEST_FILE, stopped)
                append_jsonl(LOG, stopped)
                return stopped

            if max_ticks and cycle >= max_ticks:
                complete = {
                    "ts": now(),
                    "phase": "SANDBOX_AUTOLOOP_V1",
                    "status": "completed_max_ticks",
                    "cycle_index": cycle,
                    "locks": LOCKS,
                    "paper_only": True
                }
                write_json(STATE_FILE, complete)
                write_json(LATEST_FILE, complete)
                append_jsonl(LOG, complete)
                return complete

            cycle += 1
            try:
                kernel_commentary = kernel_every > 0 and cycle % kernel_every == 0
                self.tick_once(
                    cycle_index=cycle,
                    instruments=instruments,
                    kernel_commentary=kernel_commentary
                )
            except Exception as exc:
                err = {
                    "ts": now(),
                    "phase": "SANDBOX_AUTOLOOP_V1",
                    "status": "error_safe_continue",
                    "cycle_index": cycle,
                    "error": str(exc),
                    "traceback": traceback.format_exc()[-3000:],
                    "locks": LOCKS,
                    "paper_only": True
                }
                write_json(STATE_FILE, err)
                write_json(LATEST_FILE, err)
                append_jsonl(LOG, err)

            time.sleep(interval_seconds)

    def status(self):
        state = load_json(LATEST_FILE, {})
        if not state:
            state = load_json(STATE_FILE, {})

        return {
            "phase": "SANDBOX_AUTOLOOP_V1",
            "status": state.get("status", "ready"),
            "latest_ts": state.get("ts"),
            "cycle_index": state.get("cycle_index", 0),
            "mode": "paper_only_background_loop",
            "state": state,
            "stop_requested": STOP_FILE.exists(),
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

    def request_stop(self):
        STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        STOP_FILE.write_text(now(), encoding="utf-8")
        return self.status()

    def clear_stop(self):
        STOP_FILE.unlink(missing_ok=True)
        return self.status()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tick = sub.add_parser("tick")
    p_tick.add_argument("--instruments", default=None)
    p_tick.add_argument("--kernel-commentary", action="store_true")

    p_loop = sub.add_parser("loop")
    p_loop.add_argument("--interval", type=int, default=30)
    p_loop.add_argument("--instruments", default=None)
    p_loop.add_argument("--kernel-every", type=int, default=5)
    p_loop.add_argument("--max-ticks", type=int, default=0)

    sub.add_parser("status")
    sub.add_parser("request-stop")
    sub.add_parser("clear-stop")

    args = parser.parse_args()
    loop = SandboxAutoLoop()

    if args.cmd == "tick":
        print(json.dumps(loop.tick_once(
            instruments=args.instruments,
            kernel_commentary=args.kernel_commentary
        ), indent=2))
    elif args.cmd == "loop":
        print(json.dumps(loop.loop(
            interval_seconds=args.interval,
            instruments=args.instruments,
            kernel_every=args.kernel_every,
            max_ticks=args.max_ticks
        ), indent=2))
    elif args.cmd == "status":
        print(json.dumps(loop.status(), indent=2))
    elif args.cmd == "request-stop":
        print(json.dumps(loop.request_stop(), indent=2))
    elif args.cmd == "clear-stop":
        print(json.dumps(loop.clear_stop(), indent=2))


if __name__ == "__main__":
    main()
