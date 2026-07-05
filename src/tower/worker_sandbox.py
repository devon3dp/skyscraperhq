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
