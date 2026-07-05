#!/usr/bin/env bash
# QSB Tower V1.3 — safe boot helper
# Phase: QSB_TOWER_RUNTIME_VENV_STANDARDIZATION_V1
#
# Boots the QSB Tower stack from the standardized QSB venv.
# This helper is intentionally DEFENSIVE:
#   - It must never enable execution locks.
#   - It must never enable live_trading_enabled, order_execution_enabled,
#     practice_order_execution_enabled, binance_order_execution_enabled,
#     binance_live_trading_enabled, worker_execution_enabled,
#     provider_execution_enabled, external_provider_execution_enabled,
#     openclaw_execution_enabled, openclaw_real_tool_execution_enabled,
#     autonomous_dispatch_enabled, live_dispatch_enabled,
#     direct_provider_access.
#   - It must never source the AirLLM venv (/vaults/ai/airllm_lab/.venv).
#   - It must never install or wire AirLLM into AutoLoop, trading,
#     OpenClaw, workers, providers, or execution.
#
# Usage:
#   ./scripts/qsb_boot_stack.sh
#
set -uo pipefail

QSB_ROOT=/vaults/nvme0/qsb_tower_v1
cd "$QSB_ROOT" || { echo "[qsb_boot] FATAL: cannot cd $QSB_ROOT" >&2; exit 1; }

# 1. Activate the QSB venv + PYTHONPATH
# shellcheck disable=SC1091
source "$QSB_ROOT/scripts/qsb_env.sh"

# 1a. Verify /vaults/ai mount (AirLLM lab lives there). The boot must NOT
# fail if the mount is missing — AirLLM stays advisory-only and the
# tower must still come up. We just report it loudly.
if [ -d /vaults/ai ]; then
    echo "[qsb_boot] /vaults/ai mount present"
else
    echo "[qsb_boot] WARNING: /vaults/ai mount NOT present (AirLLM advisory disabled)" >&2
fi

# 2. Conditionally source environment files (advisory only — never enables
# live trading, order execution, or any execution gate).
if [ -f "$QSB_ROOT/.env.oanda_practice" ]; then
    # shellcheck disable=SC1091
    source "$QSB_ROOT/.env.oanda_practice"
    echo "[qsb_boot] sourced .env.oanda_practice (practice-only)"
fi
if [ -f "$QSB_ROOT/.env.binance" ]; then
    # shellcheck disable=SC1091
    source "$QSB_ROOT/.env.binance"
    echo "[qsb_boot] sourced .env.binance (testnet preview-only)"
fi
if [ -f "$QSB_ROOT/.env.alpaca" ]; then
    # shellcheck disable=SC1091
    source "$QSB_ROOT/.env.alpaca"
    echo "[qsb_boot] sourced .env.alpaca (paper-only preview)"
fi

# 3. Start dashboard via existing run.sh (idempotent: caller should stop first if needed)
if [ -x "$QSB_ROOT/run.sh" ]; then
    echo "[qsb_boot] starting dashboard via run.sh"
    "$QSB_ROOT/run.sh"
else
    echo "[qsb_boot] WARNING: run.sh missing or not executable" >&2
fi

# 4. Start sidecars only if their start scripts exist (no creation here)
start_sidecar() {
    local script="$1"
    local label="$2"
    if [ -x "$QSB_ROOT/scripts/$script" ]; then
        echo "[qsb_boot] starting $label"
        "$QSB_ROOT/scripts/$script" || echo "[qsb_boot] $label returned non-zero (continuing)"
    fi
}
start_sidecar run_kernel_chat_sidecar.sh           "kernel chat sidecar"
start_sidecar run_worker_sandbox_sidecar.sh        "worker sandbox sidecar"
start_sidecar run_oanda_floor41_sidecar.sh         "OANDA Floor 41 sidecar"
start_sidecar run_openclaw_visual_sidecar.sh       "OpenClaw visual sidecar"
start_sidecar run_paper_trade_simulator_sidecar.sh "paper trade simulator sidecar"
start_sidecar run_sandbox_performance_sidecar.sh   "sandbox performance sidecar"
start_sidecar run_strategy_intelligence_sidecar.sh "strategy intelligence sidecar"
start_sidecar run_strategy_autoloop_correlation_sidecar.sh "strategy/autoloop correlation sidecar"

# 5. Start sandbox AutoLoop only if not already running
if [ -x "$QSB_ROOT/scripts/run_sandbox_autoloop.sh" ]; then
    PIDFILE="$QSB_ROOT/data/runtime/sandbox_autoloop.pid"
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "[qsb_boot] sandbox AutoLoop already running (PID $(cat "$PIDFILE"))"
    else
        echo "[qsb_boot] starting sandbox AutoLoop"
        "$QSB_ROOT/scripts/run_sandbox_autoloop.sh" || echo "[qsb_boot] AutoLoop start returned non-zero (continuing)"
    fi
fi

# 6. Status checks (best effort, never failing the boot)
echo "[qsb_boot] ---- status ----"
[ -x "$QSB_ROOT/status.sh" ] && "$QSB_ROOT/status.sh" || true
[ -x "$QSB_ROOT/scripts/sandbox_autoloop_status.sh" ] && "$QSB_ROOT/scripts/sandbox_autoloop_status.sh" | head -40 || true
[ -x "$QSB_ROOT/scripts/final_active_kernel_preflight.sh" ] && "$QSB_ROOT/scripts/final_active_kernel_preflight.sh" || true

# 7. Endpoint smoke tests (read-only — never POST, never enable execution)
echo "[qsb_boot] ---- endpoint smoke tests ----"
for url in \
    "http://127.0.0.1:8765/api/live" \
    "http://127.0.0.1:8765/api/unified" \
    "http://127.0.0.1:8765/api/kernel_chat_status"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    echo "[qsb_boot] $url -> HTTP $code"
done

# 8. Print dashboard URL + lock summary (lock_count_true should be 0)
DASHBOARD_URL="http://127.0.0.1:8765/?v=unified"
echo "[qsb_boot] dashboard URL: $DASHBOARD_URL"

# Lock summary — pulled from /api/unified, never POSTs, never modifies state.
python3 - <<'PY' 2>/dev/null || echo "[qsb_boot] could not fetch lock summary (continuing)"
import json, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/unified", timeout=3) as r:
        d = json.loads(r.read().decode("utf-8"))
except Exception as e:
    print("[qsb_boot] lock-summary fetch failed:", str(e)[:120])
    raise SystemExit(0)
print("[qsb_boot] lock_count_true:", d.get("lock_count_true"))
print("[qsb_boot] expected_lock_count_true:", d.get("expected_lock_count_true"))
print("[qsb_boot] activation_status:",
      (d.get("kernel") or {}).get("activation_status"))
print("[qsb_boot] execution_allowed:", d.get("execution_allowed"))
locks = d.get("locks") or {}
truth = sorted(k for k, v in locks.items() if v is True)
print("[qsb_boot] locks_reporting_true:", truth or "[]")
PY

echo "[qsb_boot] done."
