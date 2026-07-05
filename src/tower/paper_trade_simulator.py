#!/usr/bin/env python3
"""
QSB Tower V1.3 — Paper Trade Simulator V1

Phase: OPENCLAW_WORKER_TRADING_SIMULATION_FLOOR_V1

Reads safe registries and emits paper-only simulated trade tickets.
Does not place orders. Does not place practice orders. Does not enable
execution. Does not call providers. Does not patch worker_sandbox or
sandbox_autoloop.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/paper_trade_simulator.jsonl"

LATEST_PATH = REG / "paper_trade_simulator_latest.json"
GATE_PATH = REG / "practice_order_gate_checklist.json"

PHASE = "OPENCLAW_WORKER_TRADING_SIMULATION_FLOOR_V1"
DEFAULT_INSTRUMENTS = ("EUR_USD", "GBP_USD", "USD_JPY")

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
    "direct_provider_access": False,
}

# Classification thresholds (paper-only)
CONFIDENCE_THRESHOLD = 0.65
PAUSE_TIGHTEN_TOKENS = {"pause", "tighten", "avoid", "block", "no_trade", "reject"}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def append_jsonl(path, record):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def pip_size(instrument):
    return 0.01 if instrument.endswith("_JPY") else 0.0001


def _strategy_row(strategy, instrument):
    for r in strategy.get("results") or []:
        if isinstance(r, dict) and r.get("instrument") == instrument:
            return r
    return {}


def _by_instrument(items):
    out = {}
    for item in items or []:
        if isinstance(item, dict):
            inst = item.get("instrument")
            if inst:
                out[inst] = item
    return out


def _correlation_row(correlation, instrument):
    return _by_instrument(correlation.get("correlations") or []).get(instrument, {})


def _performance_row(performance, instrument):
    perf = performance.get("performance") or {}
    return _by_instrument(perf.get("by_instrument") or []).get(instrument, {})


def _openclaw_row(openclaw, instrument):
    return _by_instrument(openclaw.get("recommendations") or openclaw.get("latest_recommendations") or []).get(instrument, {})


def _paper_lab_row(paper_lab, instrument):
    return _by_instrument(paper_lab.get("instruments") or []).get(instrument, {})


def _ledger_recent_for(ledger, instrument):
    return [
        e for e in (ledger.get("latest_entries") or [])
        if isinstance(e, dict) and e.get("instrument") == instrument
    ]


def _ticket_id(instrument, ts):
    h = hashlib.sha1(f"{instrument}::{ts}".encode("utf-8")).hexdigest()[:10]
    return f"pt_{h}"


def _classify(corr_row, strategy_row, openclaw_row):
    """
    Return (ticket_side, reason, gate_summary).

    ticket_side: 'paper_long' | 'paper_short' | 'no_trade'
    """
    alignment = (corr_row.get("alignment_label") or "").upper()
    s_signal = (strategy_row.get("paper_signal") or "observe").lower()
    s_direction = (strategy_row.get("paper_direction") or "").lower()
    confidence = strategy_row.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    spread_gate_ok = bool(strategy_row.get("spread_gate_ok"))
    openclaw_rec = (openclaw_row.get("sandbox_recommendation") or "").lower()
    openclaw_blocks = any(tok in openclaw_rec for tok in PAUSE_TIGHTEN_TOKENS)

    gate = {
        "alignment_is_paper_bias_candidate": alignment == "PAPER_BIAS_CANDIDATE",
        "confidence_above_threshold": confidence >= CONFIDENCE_THRESHOLD,
        "openclaw_does_not_block": not openclaw_blocks,
        "spread_gate_ok": spread_gate_ok,
    }
    can_paper_trade = all(gate.values()) and s_signal in ("long_bias", "short_bias")
    if not can_paper_trade:
        if alignment == "NO_TRADE_GATE":
            reason = "no-trade gate (spread or strategy refusal)"
        elif alignment == "BIAS_DIVERGENCE":
            reason = "bias divergence — strategy and sandbox disagree"
        elif alignment in ("OBSERVE_ALIGNED_STABLE", "OBSERVE_ALIGNED_WEAK", ""):
            reason = "observe alignment — no paper bias candidate"
        elif openclaw_blocks:
            reason = f"openclaw recommends '{openclaw_rec}'"
        elif not spread_gate_ok:
            reason = "spread gate failed"
        elif confidence < CONFIDENCE_THRESHOLD:
            reason = f"confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD:.2f}"
        else:
            reason = "no paper bias candidate confirmed"
        return "no_trade", reason, gate

    side = "paper_long" if s_signal == "long_bias" else "paper_short"
    reason = (
        f"paper bias candidate · {s_direction or s_signal} · "
        f"confidence {confidence:.2f} · openclaw '{openclaw_rec or 'observe_only'}'"
    )
    return side, reason, gate


def _stop_target_distances(strategy_row, paper_lab_row):
    avg_range = strategy_row.get("avg_candle_range_pips")
    try:
        avg_range = float(avg_range) if avg_range is not None else 0.0
    except (TypeError, ValueError):
        avg_range = 0.0
    if avg_range <= 0:
        spread = paper_lab_row.get("spread_pips") or strategy_row.get("spread_pips") or 1.0
        try:
            avg_range = max(3.0, float(spread) * 4.0)
        except (TypeError, ValueError):
            avg_range = 3.0
    return {
        "stop_distance_pips": round(avg_range * 1.5, 2),
        "target_distance_pips": round(avg_range * 2.5, 2),
        "avg_candle_range_pips": round(avg_range, 2),
    }


def _risk_score(strategy_row, paper_lab_row, openclaw_row, confidence):
    spread = paper_lab_row.get("spread_pips") or strategy_row.get("spread_pips") or 1.0
    try:
        spread = float(spread)
    except (TypeError, ValueError):
        spread = 1.0
    openclaw_blocks = (openclaw_row.get("sandbox_recommendation") or "").lower() in PAUSE_TIGHTEN_TOKENS
    base = max(0.0, min(1.0, confidence))
    spread_penalty = min(0.4, spread / 10.0)
    score = base - spread_penalty - (0.25 if openclaw_blocks else 0.0)
    return round(max(0.0, min(1.0, score)), 3)


def _entry_mid(strategy_row, paper_lab_row, performance_row):
    for src in (paper_lab_row, performance_row, strategy_row):
        m = src.get("mid") if isinstance(src, dict) else None
        if isinstance(m, (int, float)):
            return m
    return None


class PaperTradeSimulator:
    def __init__(self):
        self.sources = {
            "strategy_intelligence": REG / "strategy_intelligence_latest.json",
            "strategy_autoloop_correlation": REG / "strategy_autoloop_correlation_latest.json",
            "sandbox_performance": REG / "sandbox_performance_latest.json",
            "floor41_paper_ledger": REG / "floor41_paper_ledger.json",
            "openclaw_sandbox": REG / "openclaw_sandbox_latest.json",
            "oanda_paper_strategy": REG / "oanda_paper_strategy_latest.json",
        }

    def _load_sources(self):
        return {name: load_json(p, {}) for name, p in self.sources.items()}

    def _source_health(self, sources):
        out = {}
        for name, data in sources.items():
            out[name] = {
                "loaded": bool(data),
                "latest_ts": (
                    data.get("ts")
                    or data.get("updated_ts")
                    or data.get("latest_ts")
                ),
            }
        return out

    def build(self, instruments=DEFAULT_INSTRUMENTS):
        if isinstance(instruments, str):
            instruments = [x.strip() for x in instruments.split(",") if x.strip()]
        if not instruments:
            instruments = list(DEFAULT_INSTRUMENTS)

        sources = self._load_sources()
        strategy = sources["strategy_intelligence"]
        correlation = sources["strategy_autoloop_correlation"]
        performance = sources["sandbox_performance"]
        openclaw = sources["openclaw_sandbox"]
        paper_lab = sources["oanda_paper_strategy"]
        ledger = sources["floor41_paper_ledger"]

        ts = now()
        tickets = []
        counts = {"paper_long": 0, "paper_short": 0, "no_trade": 0}

        for inst in instruments:
            s_row = _strategy_row(strategy, inst)
            corr_row = _correlation_row(correlation, inst)
            perf_row = _performance_row(performance, inst)
            oc_row = _openclaw_row(openclaw, inst)
            pl_row = _paper_lab_row(paper_lab, inst)

            side, reason, gate = _classify(corr_row, s_row, oc_row)
            counts[side] = counts.get(side, 0) + 1

            confidence = s_row.get("confidence") or 0.0
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            entry_mid = _entry_mid(s_row, pl_row, perf_row)
            distances = _stop_target_distances(s_row, pl_row)
            risk_score = _risk_score(s_row, pl_row, oc_row, confidence)

            tickets.append({
                "ticket_id": _ticket_id(inst, ts),
                "ts": ts,
                "instrument": inst,
                "suggested_side": side,
                "confidence": round(confidence, 4),
                "reason": reason,
                "alignment": corr_row.get("alignment_label") or "-",
                "current_spread_pips": s_row.get("spread_pips")
                                       or pl_row.get("spread_pips")
                                       or perf_row.get("avg_spread_pips"),
                "simulated_entry_mid": entry_mid,
                "simulated_stop_distance_pips": distances["stop_distance_pips"],
                "simulated_target_distance_pips": distances["target_distance_pips"],
                "simulated_avg_candle_range_pips": distances["avg_candle_range_pips"],
                "simulated_risk_score": risk_score,
                "openclaw_recommendation": oc_row.get("sandbox_recommendation") or "observe_only",
                "strategy_signal": s_row.get("paper_signal") or "observe",
                "strategy_direction": s_row.get("paper_direction") or "flat_observation",
                "performance_delta_pips": perf_row.get("delta_pips_total"),
                "ledger_recent_count": len(_ledger_recent_for(ledger, inst)),
                "gate_checks": gate,
                "execution_allowed": False,
                "order_created": False,
                "paper_only": True,
                "not_financial_advice": True,
                "locks": LOCKS,
            })

        report = {
            "ts": ts,
            "phase": PHASE,
            "status": "healthy",
            "mode": "paper_only_simulated_trade_tickets",
            "instruments": list(instruments),
            "ticket_counts": counts,
            "summary": {
                "paper_long": counts.get("paper_long", 0),
                "paper_short": counts.get("paper_short", 0),
                "no_trade": counts.get("no_trade", 0),
                "total": sum(counts.values()),
            },
            "sources": self._source_health(sources),
            "tickets": tickets,
            "practice_order_gate": {
                "gate_status": (load_json(GATE_PATH, {}).get("gate_status") or "CLOSED"),
                "gate_locked": True,
                "practice_order_execution_enabled": False,
            },
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True,
            "execution_allowed": False,
        }

        write_json(LATEST_PATH, report)
        write_json(RUNTIME / "paper_trade_simulator_latest.json", report)
        append_jsonl(LOG, report)
        return report

    def status(self):
        latest = load_json(LATEST_PATH, {})
        if not latest:
            return {
                "phase": PHASE,
                "status": "idle",
                "latest_ts": None,
                "ticket_counts": {"paper_long": 0, "paper_short": 0, "no_trade": 0},
                "summary": {"paper_long": 0, "paper_short": 0, "no_trade": 0, "total": 0},
                "tickets": [],
                "practice_order_gate": {
                    "gate_status": "CLOSED",
                    "gate_locked": True,
                    "practice_order_execution_enabled": False,
                },
                "locks": LOCKS,
                "paper_only": True,
                "not_financial_advice": True,
                "execution_allowed": False,
            }
        return {
            "phase": PHASE,
            "status": latest.get("status", "healthy"),
            "latest_ts": latest.get("ts"),
            "ticket_counts": latest.get("ticket_counts", {}),
            "summary": latest.get("summary", {}),
            "sources": latest.get("sources", {}),
            "tickets": latest.get("tickets", []),
            "practice_order_gate": latest.get("practice_order_gate", {
                "gate_status": "CLOSED",
                "gate_locked": True,
                "practice_order_execution_enabled": False,
            }),
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True,
            "execution_allowed": False,
        }


if __name__ == "__main__":
    print(json.dumps(PaperTradeSimulator().status(), indent=2, default=str))
