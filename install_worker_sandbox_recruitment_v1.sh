#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Worker Sandbox Recruitment V1"
echo "======================================================"
echo "Mode: sandbox workers + OANDA paper strategy tasks only"
echo "No live orders. No practice orders. No OpenClaw execution."
echo "No autonomous dispatch. No external providers."

mkdir -p data/registries data/runtime data/logs data/packets data/backups scripts tests src/tower

echo
echo "=== BACKUPS ==="
for f in \
  src/tower/worker_sandbox.py \
  src/tower/floor41_paper_ledger.py \
  data/registries/worker_sandbox_policy.json \
  data/registries/worker_sandbox_registry.json \
  data/registries/floor41_paper_ledger.json
do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_worker_sandbox_${TS}" || true
done

echo
echo "=== WRITE WORKER SANDBOX POLICY ==="
cat > data/registries/worker_sandbox_policy.json <<'JSON'
{
  "policy": "worker_sandbox_recruitment_v1",
  "version": "1.0",
  "mode": "sandbox_only",
  "purpose": "Allow sandbox worker roles to process Floor 41 OANDA paper strategy tasks without enabling real execution.",
  "sandbox_workers_enabled": true,
  "worker_execution_enabled": false,
  "provider_execution_enabled": false,
  "external_provider_execution_enabled": false,
  "openclaw_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "live_dispatch_enabled": false,
  "direct_provider_access": false,
  "live_trading_enabled": false,
  "order_execution_enabled": false,
  "practice_order_execution_enabled": false,
  "paper_trading_enabled": true,
  "allowed_floors": [
    "floor_25_agent_coordination_department",
    "floor_37_simulation_labs",
    "floor_38_sandbox_operations",
    "floor_41_oanda_trading_floor"
  ],
  "allowed_tasks": [
    "read OANDA practice pricing",
    "run paper strategy lab",
    "write paper signal ledger",
    "produce sandbox worker observations",
    "generate lift packet trails",
    "ask local-only kernel for commentary"
  ],
  "forbidden_tasks": [
    "place OANDA live orders",
    "place OANDA practice orders",
    "activate OpenClaw execution",
    "activate autonomous dispatch",
    "call external AI providers",
    "enable real worker execution"
  ]
}
JSON

echo
echo "=== WRITE SANDBOX WORKER REGISTRY ==="
cat > data/registries/worker_sandbox_registry.json <<'JSON'
{
  "registry": "worker_sandbox_registry_v1",
  "sandbox_workers_enabled": true,
  "worker_execution_enabled": false,
  "openclaw_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "workers": [
    {
      "id": "market_scout",
      "name": "Market Scout",
      "role": "Reads OANDA practice pricing and identifies quote status.",
      "home_floor": "floor_41",
      "sandbox_only": true
    },
    {
      "id": "spread_watcher",
      "name": "Spread Watcher",
      "role": "Measures spreads, quote quality, and paper signal conditions.",
      "home_floor": "floor_41",
      "sandbox_only": true
    },
    {
      "id": "risk_sentinel",
      "name": "Risk Sentinel",
      "role": "Verifies all execution locks remain closed.",
      "home_floor": "floor_30",
      "sandbox_only": true
    },
    {
      "id": "paper_strategy_analyst",
      "name": "Paper Strategy Analyst",
      "role": "Converts market metrics into paper-only strategy observations.",
      "home_floor": "floor_41",
      "sandbox_only": true
    },
    {
      "id": "kernel_commentary_runner",
      "name": "Kernel Commentary Runner",
      "role": "Routes paper-lab summaries to the local-only QSB Kernel speech layer.",
      "home_floor": "penthouse",
      "sandbox_only": true
    },
    {
      "id": "ledger_clerk",
      "name": "Ledger Clerk",
      "role": "Writes paper signals and simulated P/L markers to the ledger.",
      "home_floor": "floor_31",
      "sandbox_only": true
    }
  ]
}
JSON

echo
echo "=== CREATE FLOOR 41 PAPER LEDGER ==="
cat > src/tower/floor41_paper_ledger.py <<'PY'
#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 41 Paper Ledger

Records paper-only signal observations from the OANDA Paper Strategy Lab.

No real orders.
No practice orders.
No live trading.
No worker execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import uuid

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/floor41_paper_ledger.jsonl"

LEDGER_PATH = REG / "floor41_paper_ledger.json"

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
}


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


def pip_size(instrument):
    return 0.01 if instrument and instrument.endswith("_JPY") else 0.0001


def latest_prior_mid(entries, instrument):
    for entry in reversed(entries):
        if entry.get("instrument") == instrument and isinstance(entry.get("mid"), (int, float)):
            return entry["mid"]
    return None


class Floor41PaperLedger:
    def __init__(self):
        data = load_json(LEDGER_PATH, {})
        self.entries = data.get("entries", []) if isinstance(data, dict) else []

    def record_lab(self, lab):
        ts = datetime.now(timezone.utc).isoformat()
        new_entries = []

        instruments = lab.get("instruments", [])
        account = lab.get("account", {})

        for metric in instruments:
            instrument = metric.get("instrument")
            mid = metric.get("mid")
            prior_mid = latest_prior_mid(self.entries, instrument)
            delta = None
            delta_pips = None

            if isinstance(mid, (int, float)) and isinstance(prior_mid, (int, float)):
                delta = mid - prior_mid
                delta_pips = delta / pip_size(instrument)

            signal = metric.get("paper_signal", "observe")
            paper_direction = {
                "long_bias": "paper_long_bias",
                "short_bias": "paper_short_bias",
                "observe": "flat_observation",
                "no_trade": "flat_no_trade"
            }.get(signal, "flat_observation")

            entry = {
                "id": f"paper_{uuid.uuid4().hex[:12]}",
                "ts": ts,
                "floor": "floor_41",
                "source": "oanda_paper_strategy_lab_v1",
                "instrument": instrument,
                "paper_signal": signal,
                "paper_direction": paper_direction,
                "paper_reason": metric.get("paper_reason"),
                "bid": metric.get("bid"),
                "ask": metric.get("ask"),
                "mid": mid,
                "spread_pips": metric.get("spread_pips"),
                "top_liquidity_imbalance": metric.get("top_liquidity_imbalance"),
                "prior_mid": prior_mid,
                "simulated_delta": delta,
                "simulated_delta_pips_since_prior_observation": delta_pips,
                "account_nav": account.get("NAV"),
                "paper_only": True,
                "not_financial_advice": True,
                "locks": LOCKS
            }

            new_entries.append(entry)
            append_jsonl(LOG, entry)

        self.entries.extend(new_entries)

        ledger = {
            "ledger": "floor41_paper_ledger_v1",
            "updated_ts": ts,
            "entry_count": len(self.entries),
            "latest_entry_count": len(new_entries),
            "entries": self.entries[-500:],
            "latest_entries": new_entries,
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        write_json(LEDGER_PATH, ledger)
        write_json(RUNTIME / "floor41_paper_ledger_latest.json", ledger)
        return ledger

    def status(self):
        data = load_json(LEDGER_PATH, {})
        entries = data.get("entries", [])
        latest = data.get("latest_entries", [])

        pips = [
            e.get("simulated_delta_pips_since_prior_observation")
            for e in entries
            if isinstance(e.get("simulated_delta_pips_since_prior_observation"), (int, float))
        ]

        return {
            "ledger": "floor41_paper_ledger_v1",
            "entry_count": len(entries),
            "latest_entry_count": len(latest),
            "latest_entries": latest[-10:],
            "simulated_observation_delta_pips_total": sum(pips) if pips else 0,
            "paper_only": True,
            "not_financial_advice": True,
            "locks": LOCKS
        }


def record_lab(lab):
    return Floor41PaperLedger().record_lab(lab)


def status():
    return Floor41PaperLedger().status()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
PY

echo
echo "=== CREATE WORKER SANDBOX MODULE ==="
cat > src/tower/worker_sandbox.py <<'PY'
#!/usr/bin/env python3
"""
QSB Tower V1.3 — Worker Sandbox Recruitment V1

Sandbox-only workers run paper tasks through Floor 25, Floor 37, Floor 38,
and Floor 41.

No real workers.
No live dispatch.
No OpenClaw execution.
No orders.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import uuid

from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
from tower.floor41_paper_ledger import record_lab, status as ledger_status

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
PACKETS = ROOT / "data/packets"
LOG = ROOT / "data/logs/worker_sandbox.jsonl"

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
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


def workers():
    reg = load_json(REG / "worker_sandbox_registry.json", {})
    return reg.get("workers", [])


def make_packet(worker, src, dst, task, priority=5):
    return {
        "packet_id": f"pkt_{uuid.uuid4().hex[:12]}",
        "ts": datetime.now(timezone.utc).isoformat(),
        "worker_id": worker.get("id"),
        "worker_name": worker.get("name"),
        "sandbox_only": True,
        "source_floor": src,
        "target_floor": dst,
        "task": task,
        "priority": priority,
        "status": "delivered",
        "lift_route": f"{src} -> {dst}",
        "locks": LOCKS
    }


def ask_kernel_for_commentary(lab, ledger):
    try:
        from tower.kernel_dialogue_adapter import ask_kernel

        prompt = json.dumps({
            "worker_sandbox_phase": "WORKER_SANDBOX_RECRUITMENT_V1",
            "lab_summary": lab.get("summary", {}),
            "latest_instruments": lab.get("instruments", []),
            "ledger_status": {
                "entry_count": ledger.get("entry_count"),
                "latest_entry_count": ledger.get("latest_entry_count"),
                "simulated_observation_delta_pips_total": ledger.get("simulated_observation_delta_pips_total")
            },
            "locks": LOCKS
        }, indent=2) + """

Kernel, review this sandbox worker tick.
This is paper-only research.
Do not place orders.
Do not enable live trading.
Do not enable practice order execution.
Do not enable OpenClaw execution.
Do not enable autonomous dispatch.
Give a short operational assessment for the workers.
"""
        return ask_kernel(prompt, prefer_local_model=True)
    except Exception as exc:
        return {
            "ok": False,
            "safe_fallback": True,
            "error": str(exc)
        }


class WorkerSandbox:
    def __init__(self):
        load_local_env_file()
        self.policy = load_json(REG / "worker_sandbox_policy.json", {})
        self.registry = load_json(REG / "worker_sandbox_registry.json", {})

    def status(self):
        latest = load_json(REG / "worker_sandbox_latest_tick.json", {})
        ledger = ledger_status()

        return {
            "sandbox": "worker_sandbox_v1",
            "status": "healthy" if latest else "ready",
            "sandbox_workers_enabled": True,
            "worker_execution_enabled": False,
            "openclaw_execution_enabled": False,
            "autonomous_dispatch_enabled": False,
            "worker_count": len(workers()),
            "workers": workers(),
            "latest_tick_ts": latest.get("ts"),
            "latest_packet_count": len(latest.get("lift_packets", [])) if latest else 0,
            "ledger": ledger,
            "locks": LOCKS
        }

    def tick(self, instruments="EUR_USD,GBP_USD,USD_JPY"):
        ts = datetime.now(timezone.utc).isoformat()
        worker_list = workers()

        lab = OANDAPaperStrategyLab().run(instruments)
        ledger = record_lab(lab)

        routes = [
            ("floor_25", "floor_41", "recruit sandbox workers into OANDA paper lab"),
            ("floor_41", "floor_37", "deliver paper market metrics to simulation labs"),
            ("floor_37", "floor_38", "send simulated strategy results into sandbox containment"),
            ("floor_38", "floor_41", "return contained observations to trading floor")
        ]

        packets = []
        for idx, worker in enumerate(worker_list):
            src, dst, task = routes[idx % len(routes)]
            packet = make_packet(worker, src, dst, task)
            packets.append(packet)
            append_jsonl(PACKETS / "worker_sandbox_packets.jsonl", packet)

        kernel_commentary = ask_kernel_for_commentary(lab, ledger)

        tick = {
            "ts": ts,
            "sandbox": "worker_sandbox_v1",
            "status": "healthy",
            "mode": "sandbox_only_paper_strategy",
            "instruments": instruments,
            "sandbox_workers_enabled": True,
            "worker_execution_enabled": False,
            "openclaw_execution_enabled": False,
            "autonomous_dispatch_enabled": False,
            "lab_summary": lab.get("summary", {}),
            "ledger_status": {
                "entry_count": ledger.get("entry_count"),
                "latest_entry_count": ledger.get("latest_entry_count"),
                "simulated_observation_delta_pips_total": ledger.get("simulated_observation_delta_pips_total")
            },
            "lift_packets": packets,
            "kernel_commentary": kernel_commentary,
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        write_json(REG / "worker_sandbox_latest_tick.json", tick)
        write_json(RUNTIME / "worker_sandbox_latest_tick.json", tick)
        write_json(REG / "worker_sandbox_lift_packets_latest.json", {"packets": packets, "ts": ts})
        append_jsonl(LOG, tick)

        return tick


def status():
    return WorkerSandbox().status()


def tick(instruments="EUR_USD,GBP_USD,USD_JPY"):
    return WorkerSandbox().tick(instruments)


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
PY

echo
echo "=== CREATE SCRIPTS ==="
cat > scripts/worker_sandbox_status.sh <<'SH1'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 - <<'PY'
from tower.worker_sandbox import WorkerSandbox
import json
print(json.dumps(WorkerSandbox().status(), indent=2))
PY
SH1
chmod +x scripts/worker_sandbox_status.sh

cat > scripts/worker_sandbox_tick.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.worker_sandbox import WorkerSandbox
import json
print(json.dumps(WorkerSandbox().tick("$INSTRUMENTS"), indent=2))
PY
SH2
chmod +x scripts/worker_sandbox_tick.sh

echo
echo "=== CREATE TEST ==="
cat > tests/test_worker_sandbox_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

for rel in [
    "src/tower/floor41_paper_ledger.py",
    "src/tower/worker_sandbox.py",
]:
    py_compile.compile(str(ROOT / rel), doraise=True)

from tower.worker_sandbox import WorkerSandbox

s = WorkerSandbox().status()

assert s["sandbox"] == "worker_sandbox_v1"
assert s["sandbox_workers_enabled"] is True
assert s["worker_execution_enabled"] is False
assert s["openclaw_execution_enabled"] is False
assert s["autonomous_dispatch_enabled"] is False
assert s["worker_count"] >= 6
assert s["locks"]["live_trading_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["provider_execution_enabled"] is False
assert s["locks"]["external_provider_execution_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

print("WORKER SANDBOX V1 TEST PASSED")
print("  Worker count:", s["worker_count"])
print("  Worker execution:", s["worker_execution_enabled"])
print("  OpenClaw execution:", s["openclaw_execution_enabled"])
print("  Autonomous dispatch:", s["autonomous_dispatch_enabled"])
PY

echo
echo "=== RUN COMPILE + TEST ==="
python3 -m py_compile src/tower/floor41_paper_ledger.py
python3 -m py_compile src/tower/worker_sandbox.py
python3 tests/test_worker_sandbox_v1.py

echo
echo "=== STATUS BEFORE TICK ==="
./scripts/worker_sandbox_status.sh | head -120

echo
echo "=== RUN FIRST SANDBOX WORKER TICK ==="
./scripts/worker_sandbox_tick.sh EUR_USD,GBP_USD,USD_JPY | tee data/runtime/worker_sandbox_first_tick_output.json | head -180

echo
echo "=== STATUS AFTER TICK ==="
./scripts/worker_sandbox_status.sh | head -180

echo
echo "=== ACTIVE KERNEL PREFLIGHT ==="
./scripts/final_active_kernel_preflight.sh

echo
echo "======================================================"
echo "  WORKER SANDBOX RECRUITMENT V1 COMPLETE"
echo "======================================================"
echo "Sandbox workers recruited."
echo "Lift packets generated."
echo "Paper ledger updated."
echo "OANDA orders remain disabled."
echo "OpenClaw execution remains disabled."
echo "Autonomous dispatch remains disabled."
echo "======================================================"
