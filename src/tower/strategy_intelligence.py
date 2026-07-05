#!/usr/bin/env python3
"""
QSB Tower V1.3 — Safe Strategy Intelligence Retry V1

Standalone only.
Does not patch worker_sandbox.
Does not place orders.
Does not enable OpenClaw execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import statistics
import urllib.parse
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/strategy_intelligence.jsonl"

POLICY_PATH = REG / "strategy_intelligence_policy.json"
LATEST_PATH = REG / "strategy_intelligence_latest.json"

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
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_jsonl(path, record):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_env_file():
    env = ROOT / ".env.oanda_practice"
    if not env.exists():
        return

    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and v and k not in os.environ:
            os.environ[k] = v


def pip_size(instrument):
    return 0.01 if instrument.endswith("_JPY") else 0.0001


def avg(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.mean(values) if values else 0.0


def latest_spread_mid(instrument):
    lab = load_json(REG / "oanda_paper_strategy_latest.json", {})
    for item in lab.get("instruments", []):
        if item.get("instrument") == instrument:
            return item.get("spread_pips"), item.get("mid")
    return None, None


class StrategyIntelligence:
    def __init__(self):
        load_env_file()
        self.policy = load_json(POLICY_PATH, {})
        self.base_url = os.environ.get("OANDA_BASE_URL", "https://api-fxpractice.oanda.com").rstrip("/")
        self.token = os.environ.get("OANDA_API_TOKEN", "")

    def fetch_candles(self, instrument):
        if not self.token:
            return {
                "ok": False,
                "error": "OANDA_API_TOKEN missing",
                "candles": []
            }

        count = int(self.policy.get("candle_count", 80))
        granularity = self.policy.get("granularity", "M5")
        query = urllib.parse.urlencode({
            "count": str(count),
            "granularity": granularity,
            "price": "M"
        })
        url = f"{self.base_url}/v3/instruments/{instrument}/candles?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            candles = []
            for c in data.get("candles", []):
                mid = c.get("mid", {})
                if c.get("complete") and all(k in mid for k in ("o", "h", "l", "c")):
                    candles.append(c)

            return {
                "ok": True,
                "candles": candles,
                "granularity": granularity
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "candles": []
            }

    def max_spread(self, instrument):
        m = self.policy.get("max_spread_pips", {})
        return float(m.get(instrument, m.get("default", 1.8)))

    def momentum_gate(self, instrument):
        m = self.policy.get("momentum_gate_pips", {})
        return float(m.get(instrument, m.get("default", 0.75)))

    def analyze_one(self, instrument):
        spread, mid = latest_spread_mid(instrument)
        candles_result = self.fetch_candles(instrument)

        if not candles_result["ok"]:
            return {
                "instrument": instrument,
                "ok": False,
                "paper_signal": "observe",
                "paper_direction": "flat_observation",
                "confidence": 0.0,
                "reason": f"history unavailable: {candles_result.get('error')}",
                "execution_allowed": False,
                "paper_only": True,
                "locks": LOCKS
            }

        candles = candles_result["candles"]
        min_count = int(self.policy.get("min_complete_candles", 20))
        if len(candles) < min_count:
            return {
                "instrument": instrument,
                "ok": False,
                "paper_signal": "observe",
                "paper_direction": "flat_observation",
                "confidence": 0.0,
                "reason": f"not enough candles: {len(candles)} < {min_count}",
                "execution_allowed": False,
                "paper_only": True,
                "locks": LOCKS
            }

        pip = pip_size(instrument)
        closes = [float(c["mid"]["c"]) for c in candles]
        highs = [float(c["mid"]["h"]) for c in candles]
        lows = [float(c["mid"]["l"]) for c in candles]

        mom_3 = (closes[-1] - closes[-4]) / pip if len(closes) >= 4 else 0.0
        mom_10 = (closes[-1] - closes[-11]) / pip if len(closes) >= 11 else 0.0
        mom_20 = (closes[-1] - closes[-21]) / pip if len(closes) >= 21 else 0.0

        recent_avg = avg(closes[-5:])
        prior_avg = avg(closes[-15:-10])
        slope = (recent_avg - prior_avg) / pip if prior_avg else 0.0

        ranges = [(h - l) / pip for h, l in zip(highs[-15:], lows[-15:])]
        avg_range = avg(ranges)

        spread_known = isinstance(spread, (int, float))
        spread_ok = spread_known and spread <= self.max_spread(instrument)

        strength = min(abs(mom_10) / 6.0, 0.25) + min(abs(slope) / 5.0, 0.20)
        confidence = 0.35 + strength
        confidence += 0.15 if spread_ok else -0.10
        confidence = max(0.0, min(0.95, confidence))

        threshold = float(self.policy.get("min_confidence_for_bias", 0.62))
        gate = self.momentum_gate(instrument)

        if not spread_known:
            signal = "observe"
            direction = "flat_observation"
            reason = "spread unavailable; observing only"
        elif not spread_ok:
            signal = "no_trade"
            direction = "flat_no_trade"
            reason = f"spread gate failed: spread={spread:.2f}, max={self.max_spread(instrument):.2f}"
        elif confidence >= threshold and mom_10 >= gate and slope > 0 and mom_3 > 0:
            signal = "long_bias"
            direction = "paper_long_bias"
            reason = "upward momentum passed confidence and spread gates"
        elif confidence >= threshold and mom_10 <= -gate and slope < 0 and mom_3 < 0:
            signal = "short_bias"
            direction = "paper_short_bias"
            reason = "downward momentum passed confidence and spread gates"
        else:
            signal = "observe"
            direction = "flat_observation"
            reason = "no strong aligned candle setup"

        return {
            "instrument": instrument,
            "ok": True,
            "paper_signal": signal,
            "paper_direction": direction,
            "confidence": confidence,
            "reason": reason,
            "candles_used": len(candles),
            "granularity": candles_result.get("granularity"),
            "spread_pips": spread,
            "spread_gate_ok": spread_ok,
            "momentum_3_pips": mom_3,
            "momentum_10_pips": mom_10,
            "momentum_20_pips": mom_20,
            "avg_slope_pips": slope,
            "avg_candle_range_pips": avg_range,
            "execution_allowed": False,
            "paper_only": True,
            "not_financial_advice": True,
            "locks": LOCKS
        }

    def run(self, instruments="EUR_USD,GBP_USD,USD_JPY"):
        if isinstance(instruments, str):
            instruments = [x.strip() for x in instruments.split(",") if x.strip()]

        results = [self.analyze_one(inst) for inst in instruments]

        counts = {}
        for r in results:
            sig = r.get("paper_signal", "observe")
            counts[sig] = counts.get(sig, 0) + 1

        report = {
            "ts": now(),
            "phase": "SAFE_STRATEGY_INTELLIGENCE_RETRY_V1",
            "status": "healthy",
            "mode": "standalone_paper_only_signal_intelligence",
            "instruments": instruments,
            "signal_counts": counts,
            "results": results,
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        write_json(LATEST_PATH, report)
        write_json(RUNTIME / "strategy_intelligence_latest.json", report)
        append_jsonl(LOG, report)
        return report

    def status(self):
        latest = load_json(LATEST_PATH, {})
        return {
            "phase": "SAFE_STRATEGY_INTELLIGENCE_RETRY_V1",
            "status": latest.get("status", "ready"),
            "latest_ts": latest.get("ts"),
            "signal_counts": latest.get("signal_counts", {}),
            "results": latest.get("results", []),
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }


if __name__ == "__main__":
    print(json.dumps(StrategyIntelligence().status(), indent=2))
