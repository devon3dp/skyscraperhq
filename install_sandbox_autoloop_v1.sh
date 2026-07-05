#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Sandbox AutoLoop V1"
echo "======================================================"
echo "Mode: background paper-only loop"
echo "No live orders. No practice orders. No OpenClaw execution."
echo "No real worker execution. No autonomous dispatch."

mkdir -p data/registries data/runtime data/logs data/backups scripts tests src/tower

echo
echo "=== BACKUPS ==="
for f in \
  src/tower/sandbox_autoloop.py \
  data/registries/sandbox_autoloop_policy.json \
  data/registries/sandbox_autoloop_latest.json
do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_sandbox_autoloop_${TS}" || true
done

echo
echo "=== WRITE AUTOLOOP POLICY ==="
cat > data/registries/sandbox_autoloop_policy.json <<'JSON'
{
  "policy": "sandbox_autoloop_v1",
  "version": "1.0",
  "mode": "paper_only_background_loop",
  "default_interval_seconds": 30,
  "default_instruments": "EUR_USD,GBP_USD,USD_JPY",
  "kernel_commentary_every_n_ticks": 5,
  "autoloop_enabled": true,
  "paper_trading_enabled": true,
  "sandbox_workers_enabled": true,
  "openclaw_sandbox_enabled": true,
  "openclaw_visualization_enabled": true,
  "performance_scoring_enabled": true,
  "live_trading_enabled": false,
  "order_execution_enabled": false,
  "practice_order_execution_enabled": false,
  "worker_execution_enabled": false,
  "provider_execution_enabled": false,
  "external_provider_execution_enabled": false,
  "openclaw_execution_enabled": false,
  "openclaw_real_tool_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "live_dispatch_enabled": false,
  "direct_provider_access": false,
  "notes": "Runs repeated paper-only sandbox/performance/OpenClaw visual ticks. Does not place orders or enable execution."
}
JSON

echo
echo "=== CREATE SANDBOX AUTOLOOP MODULE ==="
cat > src/tower/sandbox_autoloop.py <<'PY'
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
PY

echo
echo "=== CREATE AUTOLOOP SCRIPTS ==="
cat > scripts/sandbox_autoloop_tick.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 src/tower/sandbox_autoloop.py tick --instruments "$INSTRUMENTS"
SH
chmod +x scripts/sandbox_autoloop_tick.sh

cat > scripts/sandbox_autoloop_status.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 src/tower/sandbox_autoloop.py status
SH
chmod +x scripts/sandbox_autoloop_status.sh

cat > scripts/run_sandbox_autoloop.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INTERVAL="${1:-30}"
INSTRUMENTS="${2:-EUR_USD,GBP_USD,USD_JPY}"
KERNEL_EVERY="${3:-5}"

PIDFILE="data/runtime/sandbox_autoloop.pid"
LOGFILE="data/logs/sandbox_autoloop.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Sandbox AutoLoop already running: PID $(cat "$PIDFILE")"
  exit 0
fi

python3 src/tower/sandbox_autoloop.py clear-stop >/dev/null

nohup python3 src/tower/sandbox_autoloop.py loop \
  --interval "$INTERVAL" \
  --instruments "$INSTRUMENTS" \
  --kernel-every "$KERNEL_EVERY" \
  > "$LOGFILE" 2>&1 &

echo $! > "$PIDFILE"
sleep 1

echo "Sandbox AutoLoop started: PID $(cat "$PIDFILE")"
echo "Interval seconds: $INTERVAL"
echo "Instruments: $INSTRUMENTS"
echo "Kernel commentary every N ticks: $KERNEL_EVERY"
echo "Log: $LOGFILE"
SH
chmod +x scripts/run_sandbox_autoloop.sh

cat > scripts/stop_sandbox_autoloop.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/sandbox_autoloop.pid"

python3 src/tower/sandbox_autoloop.py request-stop >/dev/null 2>&1 || true
sleep 2

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "Sandbox AutoLoop stopped."
./scripts/sandbox_autoloop_status.sh || true
SH
chmod +x scripts/stop_sandbox_autoloop.sh

cat > scripts/sandbox_autoloop_tail.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
tail -f data/logs/sandbox_autoloop.out
SH
chmod +x scripts/sandbox_autoloop_tail.sh

echo
echo "=== CREATE TEST ==="
cat > tests/test_sandbox_autoloop_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/sandbox_autoloop.py"), doraise=True)

from tower.sandbox_autoloop import SandboxAutoLoop

s = SandboxAutoLoop().status()

assert s["phase"] == "SANDBOX_AUTOLOOP_V1"
assert s["paper_only"] is True
assert s["not_financial_advice"] is True
assert s["locks"]["live_trading_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["worker_execution_enabled"] is False
assert s["locks"]["provider_execution_enabled"] is False
assert s["locks"]["external_provider_execution_enabled"] is False
assert s["locks"]["openclaw_execution_enabled"] is False
assert s["locks"]["openclaw_real_tool_execution_enabled"] is False
assert s["locks"]["autonomous_dispatch_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

print("SANDBOX AUTOLOOP V1 TEST PASSED")
print("  Status:", s["status"])
print("  Cycle:", s["cycle_index"])
PY

echo
echo "=== RUN COMPILE + TEST ==="
python3 -m py_compile src/tower/sandbox_autoloop.py
python3 tests/test_sandbox_autoloop_v1.py

echo
echo "=== MAKE SURE VISUAL SIDECARS ARE RUNNING ==="
./scripts/run_kernel_chat_sidecar.sh || true
./scripts/run_oanda_floor41_sidecar.sh || true
./scripts/run_worker_sandbox_sidecar.sh || true
./scripts/run_sandbox_performance_sidecar.sh || true
./scripts/run_openclaw_visual_sidecar.sh || true

echo
echo "=== RUN ONE AUTOLOOP TEST TICK ==="
./scripts/sandbox_autoloop_tick.sh EUR_USD,GBP_USD,USD_JPY | tee data/runtime/sandbox_autoloop_first_tick_output.json | head -180

echo
echo "=== START BACKGROUND AUTOLOOP ==="
./scripts/run_sandbox_autoloop.sh 30 EUR_USD,GBP_USD,USD_JPY 5

echo
echo "=== AUTOLOOP STATUS ==="
./scripts/sandbox_autoloop_status.sh | head -160

echo
echo "=== FINAL ACTIVE KERNEL PREFLIGHT ==="
./scripts/final_active_kernel_preflight.sh

echo
echo "======================================================"
echo "  SANDBOX AUTOLOOP V1 COMPLETE"
echo "======================================================"
echo "AutoLoop is running every 30 seconds."
echo "Dashboard panels will continue updating."
echo
echo "Status:"
echo "  ./scripts/sandbox_autoloop_status.sh"
echo
echo "Stop:"
echo "  ./scripts/stop_sandbox_autoloop.sh"
echo
echo "Tail log:"
echo "  ./scripts/sandbox_autoloop_tail.sh"
echo
echo "All execution locks remain closed."
echo "======================================================"
