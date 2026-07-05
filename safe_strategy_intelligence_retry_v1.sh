#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Safe Strategy Intelligence Retry V1"
echo "======================================================"
echo "Scope:"
echo "  - standalone Strategy Intelligence CLI"
echo "  - standalone Strategy Intelligence sidecar on 127.0.0.1:8771"
echo "  - NO worker_sandbox.py patch"
echo "  - NO dashboard patch"
echo "  - NO order execution"
echo "======================================================"

mkdir -p data/registries data/runtime data/logs data/backups scripts tests src/tower

echo
echo "=== 1. STOP STRATEGY SIDECAR ONLY ==="
if [ -f data/runtime/strategy_intelligence_sidecar.pid ]; then
  PID="$(cat data/runtime/strategy_intelligence_sidecar.pid || true)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f data/runtime/strategy_intelligence_sidecar.pid
fi

# Clear any process still holding port 8771, without touching other sidecars.
PIDS="$(lsof -ti tcp:8771 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  echo "Killing old port 8771 process(es): $PIDS"
  kill $PIDS || true
  sleep 1
fi

echo
echo "=== 2. BACKUP CURRENT STRATEGY FILES ==="
for f in \
  src/tower/strategy_intelligence.py \
  src/tower/strategy_intelligence_sidecar.py \
  data/registries/strategy_intelligence_policy.json \
  data/registries/strategy_intelligence_latest.json
do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_safe_strategy_retry_${TS}" || true
done

echo
echo "=== 3. VERIFY EXISTING CORE STILL COMPILES ==="
python3 - <<'PY'
import py_compile
from pathlib import Path

files = [
    "src/dashboard/server.py",
    "src/tower/worker_sandbox.py",
    "src/tower/sandbox_autoloop.py",
    "src/tower/openclaw_sandbox_layer.py",
    "src/tower/sandbox_performance_loop.py",
]

for rel in files:
    p = Path(rel)
    if p.exists():
        py_compile.compile(str(p), doraise=True)
        print("OK:", rel)
    else:
        print("MISSING:", rel)
PY

echo
echo "=== 4. WRITE SAFE POLICY ==="
cat > data/registries/strategy_intelligence_policy.json <<'JSON'
{
  "policy": "safe_strategy_intelligence_retry_v1",
  "version": "1.0",
  "mode": "standalone_paper_only_signal_intelligence",
  "environment": "oanda_practice_read_only",
  "granularity": "M5",
  "candle_count": 80,
  "min_complete_candles": 20,
  "min_confidence_for_bias": 0.62,
  "max_spread_pips": {
    "EUR_USD": 1.4,
    "GBP_USD": 1.8,
    "USD_JPY": 1.8,
    "default": 1.8
  },
  "momentum_gate_pips": {
    "default": 0.75,
    "USD_JPY": 0.75
  },
  "paper_trading_enabled": true,
  "strategy_intelligence_enabled": true,
  "history_reads_enabled": true,
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
  "direct_provider_access": false
}
JSON

echo
echo "=== 5. WRITE SAFE STANDALONE STRATEGY MODULE ==="
cat > src/tower/strategy_intelligence.py <<'PY'
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
PY

echo
echo "=== 6. WRITE SAFE SIDECAR ==="
cat > src/tower/strategy_intelligence_sidecar.py <<'PY'
#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

HOST = "127.0.0.1"
PORT = 8771


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


def send(handler, payload, code=200):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        send(self, {}, 204)

    def do_GET(self):
        load_env_file()
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

        try:
            from tower.strategy_intelligence import StrategyIntelligence
            si = StrategyIntelligence()

            if parsed.path == "/api/strategy/status":
                send(self, si.status())
            elif parsed.path == "/api/strategy/run":
                send(self, si.run(instruments))
            else:
                send(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            send(self, {"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        load_env_file()
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = {}
            if length:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments", "EUR_USD,GBP_USD,USD_JPY")

            from tower.strategy_intelligence import StrategyIntelligence
            send(self, StrategyIntelligence().run(instruments))
        except Exception as exc:
            send(self, {"ok": False, "error": str(exc)}, 500)


def main():
    print(f"Strategy Intelligence sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
PY

echo
echo "=== 7. WRITE SCRIPTS ==="
cat > scripts/strategy_intelligence_run.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.strategy_intelligence import StrategyIntelligence
import json
print(json.dumps(StrategyIntelligence().run("$INSTRUMENTS"), indent=2))
PY
SH
chmod +x scripts/strategy_intelligence_run.sh

cat > scripts/strategy_intelligence_status.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 - <<'PY'
from tower.strategy_intelligence import StrategyIntelligence
import json
print(json.dumps(StrategyIntelligence().status(), indent=2))
PY
SH
chmod +x scripts/strategy_intelligence_status.sh

cat > scripts/run_strategy_intelligence_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

PIDFILE="data/runtime/strategy_intelligence_sidecar.pid"
LOGFILE="data/logs/strategy_intelligence_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Strategy Intelligence sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/strategy_intelligence_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Strategy Intelligence sidecar started: PID $(cat "$PIDFILE")"
  echo "Status: http://127.0.0.1:8771/api/strategy/status"
else
  echo "FAILED to start Strategy Intelligence sidecar"
  tail -60 "$LOGFILE" || true
  exit 1
fi
SH
chmod +x scripts/run_strategy_intelligence_sidecar.sh

cat > scripts/stop_strategy_intelligence_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/strategy_intelligence_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" || true)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

PIDS="$(lsof -ti tcp:8771 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS || true
fi

echo "Strategy Intelligence sidecar stopped."
SH
chmod +x scripts/stop_strategy_intelligence_sidecar.sh

echo
echo "=== 8. COMPILE TEST ==="
python3 -m py_compile src/tower/strategy_intelligence.py
python3 -m py_compile src/tower/strategy_intelligence_sidecar.py
python3 -m py_compile src/dashboard/server.py
python3 -m py_compile src/tower/worker_sandbox.py

echo
echo "=== 9. RUN STRATEGY INTELLIGENCE ONCE ==="
./scripts/strategy_intelligence_run.sh EUR_USD,GBP_USD,USD_JPY | tee data/runtime/safe_strategy_intelligence_retry_first_run.json | head -220

echo
echo "=== 10. START SIDECAR AND TEST ==="
./scripts/run_strategy_intelligence_sidecar.sh
curl -s "http://127.0.0.1:8771/api/strategy/status" | python3 -m json.tool | head -180

echo
echo "=== 11. CONFIRM EXISTING SYSTEM STILL HEALTHY ==="
./scripts/sandbox_autoloop_status.sh | head -120 || true
./scripts/worker_sandbox_status.sh | head -80 || true
./scripts/final_active_kernel_preflight.sh

echo
echo "======================================================"
echo "  SAFE STRATEGY INTELLIGENCE RETRY V1 COMPLETE"
echo "======================================================"
echo "Test run:"
echo "  ./scripts/strategy_intelligence_run.sh EUR_USD,GBP_USD,USD_JPY"
echo
echo "Sidecar:"
echo "  http://127.0.0.1:8771/api/strategy/status"
echo "  http://127.0.0.1:8771/api/strategy/run"
echo
echo "No dashboard was patched."
echo "No worker sandbox file was patched."
echo "All execution locks remain closed."
echo "======================================================"
