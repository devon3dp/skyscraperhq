#!/usr/bin/env python3
"""
QSB Tower V1.3 — OpenClaw Sandbox Visual Layer V1

This is NOT real OpenClaw execution.
It makes OpenClaw candidates visible as sandbox observers and dashboard actors.

No orders.
No autonomous dispatch.
No external providers.
No real tool execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import random
import uuid

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/openclaw_sandbox_layer.jsonl"

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


def registry_workers():
    reg = load_json(REG / "openclaw_sandbox_registry.json", {})
    return reg.get("workers", [])


class OpenClawSandboxLayer:
    def status(self):
        latest = load_json(REG / "openclaw_sandbox_latest.json", {})
        perf = load_json(REG / "sandbox_performance_latest.json", {})
        worker = load_json(REG / "worker_sandbox_latest_tick.json", {})
        paper = load_json(REG / "oanda_paper_strategy_latest.json", {})

        return {
            "layer": "openclaw_sandbox_visual_layer_v1",
            "status": "healthy" if latest else "ready",
            "openclaw_sandbox_enabled": True,
            "openclaw_visualization_enabled": True,
            "openclaw_execution_enabled": False,
            "worker_count": len(registry_workers()),
            "workers": registry_workers(),
            "latest_ts": latest.get("ts"),
            "latest_packets": latest.get("packets", []),
            "latest_recommendations": latest.get("recommendations", []),
            "performance_summary": perf.get("performance", {}),
            "worker_tick_ts": worker.get("ts"),
            "paper_lab_ts": paper.get("ts"),
            "locks": LOCKS,
            "sandbox_only": True,
            "not_financial_advice": True
        }

    def tick(self):
        ts = datetime.now(timezone.utc).isoformat()
        perf = load_json(REG / "sandbox_performance_latest.json", {})
        paper = load_json(REG / "oanda_paper_strategy_latest.json", {})
        workers = registry_workers()

        perf_summary = perf.get("performance", {})
        instruments = perf_summary.get("by_instrument", [])
        paper_instruments = paper.get("instruments", [])

        recommendations = []
        for item in instruments:
            inst = item.get("instrument")
            score = item.get("paper_score_total", 0) or 0
            delta = item.get("delta_pips_total", 0) or 0
            spread = item.get("avg_spread_pips")

            if score > 0.5 and delta > 0:
                rec = "continue_observation_positive_bias"
            elif delta < -2:
                rec = "tighten_filter_or_pause_pair"
            else:
                rec = "observe_only"

            recommendations.append({
                "instrument": inst,
                "sandbox_recommendation": rec,
                "paper_score_total": score,
                "delta_pips_total": delta,
                "avg_spread_pips": spread,
                "execution_allowed": False
            })

        routes = [
            ("floor_25", "floor_41", "OpenClaw sandbox probe checks paper market state"),
            ("floor_41", "floor_37", "OpenClaw maps paper signals into simulation notes"),
            ("floor_37", "floor_38", "OpenClaw sends strategy notes into sandbox containment"),
            ("floor_38", "floor_30", "OpenClaw risk guard verifies locks"),
            ("floor_30", "floor_25", "OpenClaw returns lock report to worker coordination")
        ]

        packets = []
        for idx, worker in enumerate(workers):
            src, dst, task = routes[idx % len(routes)]
            packets.append({
                "packet_id": f"oc_pkt_{uuid.uuid4().hex[:12]}",
                "ts": ts,
                "worker_id": worker.get("id"),
                "worker_name": worker.get("name"),
                "source_floor": src,
                "target_floor": dst,
                "task": task,
                "status": "delivered",
                "sandbox_only": True,
                "execution_enabled": False,
                "lift_lane": random.randint(1, 9),
                "locks": LOCKS
            })

        state = {
            "ts": ts,
            "layer": "openclaw_sandbox_visual_layer_v1",
            "status": "healthy",
            "openclaw_sandbox_enabled": True,
            "openclaw_visualization_enabled": True,
            "openclaw_execution_enabled": False,
            "worker_count": len(workers),
            "workers": workers,
            "packets": packets,
            "recommendations": recommendations,
            "paper_lab_instruments": paper_instruments,
            "performance_summary": perf_summary,
            "locks": LOCKS,
            "sandbox_only": True,
            "not_financial_advice": True
        }

        write_json(REG / "openclaw_sandbox_latest.json", state)
        write_json(RUNTIME / "openclaw_sandbox_latest.json", state)
        append_jsonl(LOG, state)
        return state


def status():
    return OpenClawSandboxLayer().status()


def tick():
    return OpenClawSandboxLayer().tick()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
