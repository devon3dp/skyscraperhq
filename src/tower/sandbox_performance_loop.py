#!/usr/bin/env python3
"""
QSB Tower V1.3 — Sandbox Performance Loop V1

Runs repeated WorkerSandbox ticks and builds a paper-only performance report.

Safety:
- No live trading.
- No practice order execution.
- No OpenClaw execution.
- No real worker execution.
- No autonomous dispatch.
- No external provider routing.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import time
import statistics

from tower.worker_sandbox import WorkerSandbox

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/sandbox_performance_loop.jsonl"

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


def extract_latest_entries(tick):
    ledger = load_json(REG / "floor41_paper_ledger.json", {})
    return ledger.get("latest_entries", [])


def signed_signal_score(entry):
    """
    Paper-only scoring:
    - long_bias benefits from positive delta.
    - short_bias benefits from negative delta.
    - observe/no_trade score is neutral unless spread is tight.
    This is a research score, not trading advice.
    """
    signal = entry.get("paper_signal")
    delta = entry.get("simulated_delta_pips_since_prior_observation")
    spread = entry.get("spread_pips")

    if not isinstance(delta, (int, float)):
        delta = 0.0

    if signal == "long_bias":
        return delta
    if signal == "short_bias":
        return -delta
    if signal == "observe":
        if isinstance(spread, (int, float)) and spread <= 1.5:
            return 0.05
        return 0.0
    return 0.0


def summarize_entries(entries):
    by_inst = {}
    for e in entries:
        inst = e.get("instrument", "UNKNOWN")
        by_inst.setdefault(inst, {
            "instrument": inst,
            "entries": 0,
            "signals": {},
            "delta_pips": [],
            "scores": [],
            "avg_spread_pips": []
        })

        bucket = by_inst[inst]
        bucket["entries"] += 1
        sig = e.get("paper_signal", "unknown")
        bucket["signals"][sig] = bucket["signals"].get(sig, 0) + 1

        d = e.get("simulated_delta_pips_since_prior_observation")
        if isinstance(d, (int, float)):
            bucket["delta_pips"].append(d)

        s = e.get("spread_pips")
        if isinstance(s, (int, float)):
            bucket["avg_spread_pips"].append(s)

        bucket["scores"].append(signed_signal_score(e))

    out = []
    for inst, b in by_inst.items():
        deltas = b["delta_pips"]
        spreads = b["avg_spread_pips"]
        scores = b["scores"]

        out.append({
            "instrument": inst,
            "entries": b["entries"],
            "signals": b["signals"],
            "delta_pips_total": sum(deltas) if deltas else 0,
            "delta_pips_avg": statistics.mean(deltas) if deltas else 0,
            "avg_spread_pips": statistics.mean(spreads) if spreads else None,
            "paper_score_total": sum(scores) if scores else 0,
            "paper_score_avg": statistics.mean(scores) if scores else 0
        })

    return sorted(out, key=lambda x: x["instrument"])


def ask_kernel(report):
    try:
        from tower.kernel_dialogue_adapter import ask_kernel

        compact = {
            "phase": "SANDBOX_PERFORMANCE_LOOP_V1",
            "mode": report.get("mode"),
            "ticks_completed": report.get("ticks_completed"),
            "instruments": report.get("instruments"),
            "performance": report.get("performance"),
            "locks": LOCKS
        }

        prompt = json.dumps(compact, indent=2) + """

Kernel, review this sandbox performance loop.
This is paper-only research.
Do not place orders.
Do not enable live trading.
Do not enable practice order execution.
Do not enable OpenClaw.
Do not enable autonomous dispatch.
Give a concise performance review and next sandbox-only adjustment.
"""
        return ask_kernel(prompt, prefer_local_model=True)
    except Exception as exc:
        return {
            "ok": False,
            "safe_fallback": True,
            "error": str(exc)
        }


class SandboxPerformanceLoop:
    def __init__(self):
        load_local_env_file()
        self.policy = load_json(REG / "sandbox_performance_policy.json", {})

    def run(self, ticks=None, delay_seconds=None, instruments=None, kernel_commentary=True):
        if ticks is None:
            ticks = int(self.policy.get("default_ticks", 5))
        if delay_seconds is None:
            delay_seconds = int(self.policy.get("default_delay_seconds", 10))
        if instruments is None:
            instruments = ",".join(self.policy.get("default_instruments", ["EUR_USD", "GBP_USD", "USD_JPY"]))

        started = datetime.now(timezone.utc).isoformat()
        tick_reports = []
        all_entries = []

        sandbox = WorkerSandbox()

        for i in range(ticks):
            tick = sandbox.tick(instruments)
            entries = extract_latest_entries(tick)
            all_entries.extend(entries)

            tick_reports.append({
                "tick_index": i + 1,
                "ts": tick.get("ts"),
                "status": tick.get("status"),
                "packet_count": len(tick.get("lift_packets", [])),
                "lab_summary": tick.get("lab_summary", {}),
                "latest_entries": entries,
                "locks": LOCKS
            })

            if i < ticks - 1 and delay_seconds > 0:
                time.sleep(delay_seconds)

        performance_by_instrument = summarize_entries(all_entries)
        total_score = sum(x["paper_score_total"] for x in performance_by_instrument)
        total_delta = sum(x["delta_pips_total"] for x in performance_by_instrument)

        report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "started_ts": started,
            "phase": "SANDBOX_PERFORMANCE_LOOP_V1",
            "mode": "paper_only_sandbox_performance",
            "ticks_requested": ticks,
            "ticks_completed": len(tick_reports),
            "delay_seconds": delay_seconds,
            "instruments": instruments,
            "worker_count": len(load_json(REG / "worker_sandbox_registry.json", {}).get("workers", [])),
            "performance": {
                "entries_analyzed": len(all_entries),
                "total_paper_score": total_score,
                "total_observation_delta_pips": total_delta,
                "by_instrument": performance_by_instrument
            },
            "tick_reports": tick_reports[-20:],
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        if kernel_commentary:
            report["kernel_commentary"] = ask_kernel(report)

        write_json(REG / "sandbox_performance_latest.json", report)
        write_json(RUNTIME / "sandbox_performance_latest.json", report)
        append_jsonl(LOG, report)

        return report

    def status(self):
        latest = load_json(REG / "sandbox_performance_latest.json", {})
        return {
            "phase": "SANDBOX_PERFORMANCE_LOOP_V1",
            "status": "healthy" if latest else "ready",
            "latest_ts": latest.get("ts"),
            "ticks_completed": latest.get("ticks_completed"),
            "worker_count": latest.get("worker_count"),
            "performance": latest.get("performance", {}),
            "kernel_commentary_ok": latest.get("kernel_commentary", {}).get("ok"),
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }


def run(ticks=5, delay_seconds=10, instruments="EUR_USD,GBP_USD,USD_JPY"):
    return SandboxPerformanceLoop().run(ticks, delay_seconds, instruments)


def status():
    return SandboxPerformanceLoop().status()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
