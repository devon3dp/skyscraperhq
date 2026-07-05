"""
QSB Phase V2 — Pre-change Snapshot
Phase: QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2

Records the state of worker registries, OpenClaw state, paper/testnet
trade state, and dashboard surface BEFORE this phase makes any changes.

Read-only. No network calls. No order placement. No execution flips.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

SNAPSHOT_REG = REG / "qsb_phase_v2_prechange_snapshot.json"
SNAPSHOT_LOG = LOGS / "qsb_phase_v2_prechange.txt"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name):
    p = REG / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_load_error": str(exc)[:160]}


def _count_workers_in(blob, list_keys=("workers", "candidates", "slots",
                                        "items", "registry", "data")):
    if blob is None:
        return None
    if isinstance(blob, list):
        return len(blob)
    if isinstance(blob, dict):
        for k in list_keys:
            v = blob.get(k)
            if isinstance(v, list):
                return len(v)
        # Sometimes worker counts are reported in top-level fields.
        for k in ("worker_count", "count", "total_workers", "total"):
            v = blob.get(k)
            if isinstance(v, int):
                return v
    return None


def build_snapshot():
    sources = {
        "workers.json":                    None,
        "recruitment_workers.json":        None,
        "agent_worker_slots.json":         None,
        "coding_worker_slots.json":        None,
        "model_routing_worker_slots.json": None,
        "model_worker_slots.json":         None,
        "sandbox_extended_workers.json":   None,
        "worker_sandbox_registry.json":    None,
        "openclaw_candidate_registry.json":None,
        "openclaw_sandbox_registry.json":  None,
        "external_worker_candidates.json": None,
        "worker_candidate_registry.json":  None,
        "worker_onboarding_queue.json":    None,
    }
    for name in list(sources):
        sources[name] = _count_workers_in(_load(name))

    openclaw_state = _load("openclaw_sandbox_latest.json") or {}
    binance_state = _load("binance_paper_strategy_latest.json") or {}
    oanda_state = _load("oanda_paper_strategy_latest.json") or {}
    floor41_ledger = _load("floor41_paper_ledger.json") or {}
    floor30 = _load("kernel_activation_report.json") or {}
    intro = _load("eqsb_kernel_introspection_latest.json") or {}
    sym_graph = _load("eqsb_symbolic_graph.json") or {}

    eqsb_worker_nodes = 0
    for n in (sym_graph.get("nodes") or []):
        if n.get("kind") == "worker":
            eqsb_worker_nodes += 1

    payload = {
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_phase_v2_prechange_snapshot",
        "generated_ts": _now(),
        "worker_sources": sources,
        "worker_sources_total_reported": sum(v for v in sources.values()
                                              if isinstance(v, int)),
        "eqsb_symbolic_graph_worker_nodes": eqsb_worker_nodes,
        "kernel_workers_summary": {
            "rebased_kernel_status_total_beliefs":
                intro.get("beliefs", {}).get("belief_count"),
            "rebased_kernel_symbol_count":
                intro.get("symbols", {}).get("symbol_count"),
        },
        "openclaw_prechange": {
            "openclaw_sandbox_enabled": openclaw_state.get("openclaw_sandbox_enabled"),
            "openclaw_visualization_enabled": openclaw_state.get("openclaw_visualization_enabled"),
            "openclaw_execution_enabled": openclaw_state.get("openclaw_execution_enabled"),
            "worker_count": openclaw_state.get("worker_count"),
            "status": openclaw_state.get("status"),
            "ts": openclaw_state.get("ts"),
        },
        "binance_paper_prechange": {
            "mode": binance_state.get("mode"),
            "environment": binance_state.get("environment"),
            "default_symbols": binance_state.get("default_symbols"),
            "signal_counts": binance_state.get("signal_counts"),
            "ts": binance_state.get("ts"),
        },
        "oanda_paper_prechange": {
            "mode": oanda_state.get("mode"),
            "ts": oanda_state.get("ts"),
        },
        "floor41_ledger_prechange": {
            "entry_count": floor41_ledger.get("entry_count"),
            "latest_entry_count": floor41_ledger.get("latest_entry_count"),
            "updated_ts": floor41_ledger.get("updated_ts"),
        },
        "kernel_activation_prechange": {
            "activation_status": floor30.get("activation_status"),
            "active_kernel_source": floor30.get("active_kernel_source"),
        },
        "active_local_only": True,
        "advisory_only": True,
        "execution_allowed": False,
        "paper_only": True,
        "real_money_live_trading_enabled": False,
    }
    SNAPSHOT_REG.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_REG.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    SNAPSHOT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_LOG.open("w", encoding="utf-8") as f:
        f.write("QSB Phase V2 — Pre-change snapshot\n")
        f.write("=" * 56 + "\n")
        f.write("ts: " + payload["generated_ts"] + "\n")
        f.write("phase: " + payload["phase"] + "\n\n")
        f.write("Worker source counts:\n")
        for name, n in sources.items():
            f.write("  %-40s  %s\n" % (name, n))
        f.write("\n")
        f.write("Worker sources total reported: %d\n" %
                payload["worker_sources_total_reported"])
        f.write("EQSB symbolic graph worker nodes: %d\n" % eqsb_worker_nodes)
        f.write("\nOpenClaw pre-change:\n")
        for k, v in payload["openclaw_prechange"].items():
            f.write("  %-32s  %s\n" % (k, v))
        f.write("\nBinance paper pre-change:\n")
        for k, v in payload["binance_paper_prechange"].items():
            f.write("  %-32s  %s\n" % (k, v))
        f.write("\nFloor 41 ledger pre-change:\n")
        for k, v in payload["floor41_ledger_prechange"].items():
            f.write("  %-32s  %s\n" % (k, v))
        f.write("\nKernel activation pre-change:\n")
        for k, v in payload["kernel_activation_prechange"].items():
            f.write("  %-32s  %s\n" % (k, v))
        f.write("\nGuarantees:\n")
        f.write("  execution_allowed              False\n")
        f.write("  real_money_live_trading        False\n")
        f.write("  active_local_only              True\n")
    return payload


def main():
    print(json.dumps(build_snapshot(), indent=2))


if __name__ == "__main__":
    main()
