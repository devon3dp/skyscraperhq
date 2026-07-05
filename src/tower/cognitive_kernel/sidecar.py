"""Cognitive Kernel Tick Sidecar.

Runs orchestrator().tick() on a fixed cadence so cognition stays warm
between chat turns. Listens for SIGTERM/SIGINT and exits cleanly.

Safety contract (every cycle):
  - execution_allowed = False
  - external_api_calls_enabled = False
  - no torch / oanda / binance / stocks calls from the cognitive layers
  - on any unhandled exception inside a tick we LOG and continue
    (one bad tick must not halt cognition; persistent failure is
    surfaced via the heartbeat registry)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import argparse
import json
import os
import signal
import sys
import time
import traceback

from . import ROOT, COG_REG, COG_LOG, SAFETY, append_log, write_registry, now
from .orchestrator import orchestrator


# Default cadence; can be overridden via --interval
DEFAULT_INTERVAL_S = 30
PIDFILE = ROOT / "data/run/qsb_cognitive_sidecar.pid"
HEARTBEAT_REG = "cognitive_sidecar_heartbeat.json"


_STOP = False


def _handle_stop(signum, frame):
    global _STOP
    _STOP = True


def _ensure_pidfile_writable() -> None:
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)


def _existing_pid() -> Optional[int]:
    if not PIDFILE.exists():
        return None
    try:
        pid = int(PIDFILE.read_text().strip())
    except Exception:
        return None
    if pid <= 0:
        return None
    # Probe with signal 0
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def write_heartbeat(cycle: int, last_tick_id: Optional[str],
                     last_duration_s: float, error: Optional[str] = None) -> None:
    write_registry(HEARTBEAT_REG, {
        "ok": error is None,
        "kind": "cognitive_sidecar_heartbeat",
        "generated_ts": now(),
        "pid": os.getpid(),
        "cycle": cycle,
        "last_tick_id": last_tick_id,
        "last_duration_s": round(last_duration_s, 4),
        "last_error": error,
        "policy": "Sidecar runs cognition only. Kernel THINKS, SPEAKS, PROPOSES — never DOES.",
        "safety_envelope": dict(SAFETY),
    })


def run(interval_s: float = DEFAULT_INTERVAL_S,
        max_cycles: Optional[int] = None,
        reflect_every_n: int = 5,
        causal_every_n: int = 20) -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    existing = _existing_pid()
    if existing is not None:
        print(f"[sidecar] another sidecar already running at PID {existing}; refusing to start",
              file=sys.stderr)
        return 2

    _ensure_pidfile_writable()
    PIDFILE.write_text(str(os.getpid()))
    append_log("sidecar.jsonl",
               {"event": "start", "pid": os.getpid(),
                "interval_s": interval_s, "max_cycles": max_cycles})

    cycle = 0
    consecutive_errors = 0
    try:
        while not _STOP:
            cycle += 1
            t0 = time.time()
            err = None
            last_tick_id = None
            try:
                do_reflection = (cycle % reflect_every_n == 1)
                do_causal = (cycle % causal_every_n == 1)
                result = orchestrator().tick(
                    do_self_model_refresh=(cycle % 10 == 1),
                    do_reflection=do_reflection,
                    do_causal_predict=do_causal,
                )
                last_tick_id = result.tick_id
                consecutive_errors = 0
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                consecutive_errors += 1
                append_log("sidecar.jsonl", {
                    "event": "tick_error", "cycle": cycle,
                    "error": err, "trace": traceback.format_exc()[:2000],
                })
            duration = time.time() - t0
            write_heartbeat(cycle, last_tick_id, duration, err)
            if max_cycles is not None and cycle >= max_cycles:
                break
            # Sleep in small slices so SIGTERM is responsive
            remaining = max(0.0, interval_s - duration)
            slept = 0.0
            while slept < remaining and not _STOP:
                step = min(0.5, remaining - slept)
                time.sleep(step)
                slept += step
            # Abort entirely if we get a string of failures
            if consecutive_errors >= 10:
                append_log("sidecar.jsonl",
                           {"event": "abort_consecutive_errors",
                            "consecutive_errors": consecutive_errors})
                break
    finally:
        try:
            if PIDFILE.exists():
                PIDFILE.unlink()
        except Exception:
            pass
        append_log("sidecar.jsonl",
                   {"event": "stop", "cycle": cycle,
                    "consecutive_errors": consecutive_errors})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="QSB Cognitive Kernel tick sidecar (advisory only).")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S,
                        help="seconds between ticks (default 30)")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="stop after N cycles (default: run forever)")
    parser.add_argument("--reflect-every", type=int, default=5,
                        help="run Reflection every N ticks (default 5)")
    parser.add_argument("--causal-every", type=int, default=20,
                        help="run CausalPhaseModel every N ticks (default 20)")
    args = parser.parse_args(argv)
    return run(
        interval_s=args.interval,
        max_cycles=args.max_cycles,
        reflect_every_n=args.reflect_every,
        causal_every_n=args.causal_every,
    )


if __name__ == "__main__":
    sys.exit(main())
