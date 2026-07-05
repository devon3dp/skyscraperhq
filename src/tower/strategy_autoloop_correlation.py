#!/usr/bin/env python3
"""
QSB Tower V1.3 — Strategy <-> AutoLoop Correlation Panel V1

Read-only correlation layer.
Does not patch worker_sandbox.
Does not patch sandbox_autoloop.
Does not place orders.
Does not enable execution.
Does not enable practice orders.
Does not enable OpenClaw execution.
Does not enable autonomous dispatch.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/strategy_autoloop_correlation.jsonl"

LATEST_PATH = REG / "strategy_autoloop_correlation_latest.json"

PHASE = "STRATEGY_AUTOLOOP_CORRELATION_PANEL_V1"

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

ALIGNMENT_LABELS = {
    "OBSERVE_ALIGNED_STABLE",
    "OBSERVE_ALIGNED_WEAK",
    "PAPER_BIAS_CANDIDATE",
    "BIAS_DIVERGENCE",
    "NO_TRADE_GATE",
}


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


def _by_instrument(items, key="instrument"):
    out = {}
    for item in items or []:
        if isinstance(item, dict):
            inst = item.get(key)
            if inst:
                out[inst] = item
    return out


def _strategy_row(strategy, instrument):
    for r in strategy.get("results") or []:
        if isinstance(r, dict) and r.get("instrument") == instrument:
            return r
    return {}


def _autoloop_perf_row(autoloop, instrument):
    state = autoloop.get("state") or {}
    perf = state.get("performance") or autoloop.get("performance") or {}
    return _by_instrument(perf.get("by_instrument") or []).get(instrument, {})


def _autoloop_openclaw_row(autoloop, instrument):
    state = autoloop.get("state") or {}
    oc = state.get("openclaw_sandbox") or autoloop.get("openclaw_sandbox") or {}
    return _by_instrument(oc.get("recommendations") or []).get(instrument, {})


def _performance_row(performance, instrument):
    perf = performance.get("performance") or {}
    return _by_instrument(perf.get("by_instrument") or []).get(instrument, {})


def _paper_lab_row(paper_lab, instrument):
    return _by_instrument(paper_lab.get("instruments") or []).get(instrument, {})


def _openclaw_row(openclaw, instrument):
    return _by_instrument(openclaw.get("recommendations") or openclaw.get("latest_recommendations") or []).get(instrument, {})


def _ledger_rows(ledger, instrument):
    latest = ledger.get("latest_entries") or []
    return [e for e in latest if isinstance(e, dict) and e.get("instrument") == instrument]


def _classify(strategy_row, perf_row, paper_lab_row, openclaw_row):
    """
    Compute alignment label from joined registry rows.

    Outputs one of:
      OBSERVE_ALIGNED_STABLE — strategy + paper + openclaw all flat/observe, confidence comfortable.
      OBSERVE_ALIGNED_WEAK   — same observe alignment but strategy confidence is borderline.
      PAPER_BIAS_CANDIDATE   — strategy says long/short bias, openclaw is not against it.
      BIAS_DIVERGENCE        — strategy and paper/openclaw disagree on direction.
      NO_TRADE_GATE          — spread gate failed or strategy explicitly returns no_trade.
    """

    s_signal = (strategy_row.get("paper_signal") or "observe").lower()
    s_conf = strategy_row.get("confidence")
    try:
        s_conf = float(s_conf) if s_conf is not None else None
    except (TypeError, ValueError):
        s_conf = None

    spread_gate_ok = strategy_row.get("spread_gate_ok")
    paper_signal = (paper_lab_row.get("paper_signal") or "observe").lower()
    openclaw_rec = (openclaw_row.get("sandbox_recommendation") or "").lower()
    openclaw_exec_allowed = openclaw_row.get("execution_allowed")

    delta_pips = perf_row.get("delta_pips_total")
    try:
        delta_pips = float(delta_pips) if delta_pips is not None else 0.0
    except (TypeError, ValueError):
        delta_pips = 0.0

    if s_signal == "no_trade" or spread_gate_ok is False:
        return "NO_TRADE_GATE"

    if s_signal in ("long_bias", "short_bias"):
        bias_dir = 1 if s_signal == "long_bias" else -1
        delta_dir = 1 if delta_pips > 0.2 else (-1 if delta_pips < -0.2 else 0)
        paper_against_bias = (
            (bias_dir == 1 and paper_signal in ("short_bias", "short", "sell"))
            or (bias_dir == -1 and paper_signal in ("long_bias", "long", "buy"))
        )
        openclaw_against = openclaw_rec in ("avoid", "block", "no_trade", "reject")
        delta_against = (bias_dir == 1 and delta_dir == -1) or (bias_dir == -1 and delta_dir == 1)

        if paper_against_bias or openclaw_against or delta_against:
            return "BIAS_DIVERGENCE"
        return "PAPER_BIAS_CANDIDATE"

    paper_observe = paper_signal in ("observe", "flat", "")
    openclaw_observe = openclaw_rec in ("observe_only", "observe", "flat", "")
    if paper_observe and openclaw_observe and openclaw_exec_allowed is not True:
        if s_conf is not None and s_conf >= 0.70:
            return "OBSERVE_ALIGNED_STABLE"
        return "OBSERVE_ALIGNED_WEAK"

    return "BIAS_DIVERGENCE"


def _action_text(label, strategy_row, perf_row):
    delta = perf_row.get("delta_pips_total")
    try:
        delta = float(delta) if delta is not None else 0.0
    except (TypeError, ValueError):
        delta = 0.0

    if label == "OBSERVE_ALIGNED_STABLE":
        return "All sources aligned on observe; no paper bias forming. Continue passive watch."
    if label == "OBSERVE_ALIGNED_WEAK":
        return "Observe alignment with low confidence. Wait for clearer candle setup."
    if label == "PAPER_BIAS_CANDIDATE":
        direction = strategy_row.get("paper_direction") or strategy_row.get("paper_signal") or "bias"
        return f"Paper bias candidate ({direction}); execution locked. Continue monitoring as observation only."
    if label == "BIAS_DIVERGENCE":
        return f"Strategy and sandbox disagree (paper delta {delta:+.2f} pips). Hold; no paper bias confirmed."
    if label == "NO_TRADE_GATE":
        return "Spread or no-trade gate failed. Observation only; no bias evaluation."
    return "No action; observation only."


class StrategyAutoloopCorrelation:
    def __init__(self):
        self.registries = {
            "strategy_intelligence": REG / "strategy_intelligence_latest.json",
            "sandbox_autoloop": REG / "sandbox_autoloop_latest.json",
            "sandbox_performance": REG / "sandbox_performance_latest.json",
            "worker_sandbox": REG / "worker_sandbox_latest_tick.json",
            "floor41_paper_ledger": REG / "floor41_paper_ledger.json",
            "openclaw_sandbox": REG / "openclaw_sandbox_latest.json",
            "oanda_paper_strategy": REG / "oanda_paper_strategy_latest.json",
        }

    def _sources(self):
        return {name: load_json(path, {}) for name, path in self.registries.items()}

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

        sources = self._sources()
        strategy = sources["strategy_intelligence"]
        autoloop = sources["sandbox_autoloop"]
        performance = sources["sandbox_performance"]
        paper_lab = sources["oanda_paper_strategy"]
        openclaw = sources["openclaw_sandbox"]
        ledger = sources["floor41_paper_ledger"]

        correlations = []
        label_counts = {label: 0 for label in ALIGNMENT_LABELS}

        for inst in instruments:
            s_row = _strategy_row(strategy, inst)
            perf_row = _performance_row(performance, inst)
            if not perf_row:
                perf_row = _autoloop_perf_row(autoloop, inst)
            paper_row = _paper_lab_row(paper_lab, inst)
            openclaw_row = _openclaw_row(openclaw, inst)
            if not openclaw_row:
                openclaw_row = _autoloop_openclaw_row(autoloop, inst)
            ledger_rows = _ledger_rows(ledger, inst)

            label = _classify(s_row, perf_row, paper_row, openclaw_row)
            label_counts[label] = label_counts.get(label, 0) + 1

            correlations.append({
                "instrument": inst,
                "strategy_signal": s_row.get("paper_signal") or "observe",
                "strategy_direction": s_row.get("paper_direction") or "flat_observation",
                "strategy_confidence": s_row.get("confidence"),
                "strategy_momentum_3_pips": s_row.get("momentum_3_pips"),
                "strategy_momentum_10_pips": s_row.get("momentum_10_pips"),
                "strategy_momentum_20_pips": s_row.get("momentum_20_pips"),
                "strategy_avg_slope_pips": s_row.get("avg_slope_pips"),
                "strategy_spread_pips": s_row.get("spread_pips"),
                "strategy_spread_gate_ok": s_row.get("spread_gate_ok"),
                "strategy_reason": s_row.get("reason"),
                "paper_signal": paper_row.get("paper_signal") or "observe",
                "paper_reason": paper_row.get("paper_reason"),
                "paper_spread_pips": paper_row.get("spread_pips"),
                "paper_bid": paper_row.get("bid"),
                "paper_ask": paper_row.get("ask"),
                "paper_mid": paper_row.get("mid"),
                "performance_delta_pips": perf_row.get("delta_pips_total"),
                "performance_delta_pips_avg": perf_row.get("delta_pips_avg"),
                "performance_paper_score_total": perf_row.get("paper_score_total"),
                "performance_paper_score_avg": perf_row.get("paper_score_avg"),
                "performance_avg_spread_pips": perf_row.get("avg_spread_pips"),
                "openclaw_recommendation": openclaw_row.get("sandbox_recommendation") or "observe_only",
                "openclaw_paper_score_total": openclaw_row.get("paper_score_total"),
                "openclaw_delta_pips_total": openclaw_row.get("delta_pips_total"),
                "openclaw_execution_allowed": False,
                "ledger_recent_entries": len(ledger_rows),
                "alignment_label": label,
                "action_text": _action_text(label, s_row, perf_row),
                "execution_allowed": False,
                "paper_only": True,
                "not_financial_advice": True,
                "locks": LOCKS,
            })

        report = {
            "ts": now(),
            "phase": PHASE,
            "status": "healthy",
            "mode": "read_only_correlation_panel",
            "instruments": list(instruments),
            "label_counts": label_counts,
            "summary": {
                "observe_aligned_stable": label_counts.get("OBSERVE_ALIGNED_STABLE", 0),
                "observe_aligned_weak": label_counts.get("OBSERVE_ALIGNED_WEAK", 0),
                "paper_bias_candidates": label_counts.get("PAPER_BIAS_CANDIDATE", 0),
                "bias_divergences": label_counts.get("BIAS_DIVERGENCE", 0),
                "no_trade_gates": label_counts.get("NO_TRADE_GATE", 0),
            },
            "sources": self._source_health(sources),
            "correlations": correlations,
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True,
            "execution_allowed": False,
        }

        write_json(LATEST_PATH, report)
        write_json(RUNTIME / "strategy_autoloop_correlation_latest.json", report)
        append_jsonl(LOG, report)
        return report

    def status(self):
        latest = load_json(LATEST_PATH, {})
        if not latest:
            return {
                "phase": PHASE,
                "status": "idle",
                "latest_ts": None,
                "label_counts": {label: 0 for label in ALIGNMENT_LABELS},
                "summary": {
                    "observe_aligned_stable": 0,
                    "observe_aligned_weak": 0,
                    "paper_bias_candidates": 0,
                    "bias_divergences": 0,
                    "no_trade_gates": 0,
                },
                "correlations": [],
                "locks": LOCKS,
                "paper_only": True,
                "not_financial_advice": True,
                "execution_allowed": False,
            }
        return {
            "phase": PHASE,
            "status": latest.get("status", "healthy"),
            "latest_ts": latest.get("ts"),
            "label_counts": latest.get("label_counts", {}),
            "summary": latest.get("summary", {}),
            "sources": latest.get("sources", {}),
            "correlations": latest.get("correlations", []),
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True,
            "execution_allowed": False,
        }


if __name__ == "__main__":
    print(json.dumps(StrategyAutoloopCorrelation().status(), indent=2, default=str))
