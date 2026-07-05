#!/usr/bin/env bash
# QSB Kernel — Cognitive Tick
# Runs every cognitive module in dependency order, writes
# data/registries/qsb_kernel_cognitive_tick_latest.json, appends
# data/logs/qsb_kernel_cognitive_tick.jsonl.
#
# Read-only, advisory only. Never enables execution, workers, OpenClaw,
# providers, payments, or trading. Never exposes secrets.

set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$QSB_ROOT"
source scripts/qsb_env.sh 2>/dev/null || true

export PYTHONPATH="${QSB_ROOT}/src:${PYTHONPATH:-}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="data/logs"
REG_DIR="data/registries"
TICK_LOG="$LOG_DIR/qsb_kernel_cognitive_tick.jsonl"
TICK_REG="$REG_DIR/qsb_kernel_cognitive_tick_latest.json"

mkdir -p "$LOG_DIR" "$REG_DIR"

# Hard safety guard — assert no execution gate is being requested via env.
for gate in QSB_WORKER_EXECUTION_ENABLE QSB_PROVIDER_EXECUTION_ENABLE \
            QSB_LIVE_TRADING_ENABLE QSB_OPENCLAW_EXECUTION_ENABLE \
            QSB_AUTONOMOUS_DISPATCH_ENABLE; do
    if [ "${!gate:-}" = "1" ] || [ "${!gate:-}" = "true" ]; then
        echo "[cognitive_tick] REFUSED: $gate is set; cognitive tick is advisory-only." >&2
        exit 2
    fi
done

run_module() {
    local label="$1"
    local module="$2"
    local out
    if ! out="$(python3 -m "tower.${module}" 2>&1)"; then
        echo "[cognitive_tick] WARN: ${label} returned nonzero" >&2
        echo "$out" >&2
        printf '{"module":"%s","ok":false,"error":%s}' \
               "$label" "$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[:400]))')"
        return 0
    fi
    # We expect a single JSON document on stdout.
    if printf '%s' "$out" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' >/dev/null 2>&1; then
        printf '%s' "$out"
    else
        printf '{"module":"%s","ok":true,"stdout":%s}' \
               "$label" "$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[:400]))')"
    fi
    return 0
}

# ── Pass 1: seed every cognitive registry so cross-references resolve. ──
run_module perception kernel_perception_layer >/dev/null
run_module attention kernel_attention_layer >/dev/null
run_module working_memory kernel_working_memory >/dev/null
run_module self_model kernel_self_model >/dev/null
run_module reflection kernel_reflection_layer >/dev/null
run_module learning_assimilation kernel_learning_assimilation >/dev/null
run_module goal_stack kernel_goal_stack >/dev/null
run_module curiosity_queue kernel_curiosity_queue >/dev/null
run_module opencore_supervision_bridge kernel_opencore_supervision_bridge >/dev/null

# ── Pass 2: re-run with every registry now present so each layer sees
# the freshest cross-evidence (e.g. attention no longer flags its own
# absence; reflection has the finished opencore tickets). Read-only.
PERCEPTION_JSON="$(run_module perception kernel_perception_layer)"
ATTENTION_JSON="$(run_module attention kernel_attention_layer)"
WORKING_JSON="$(run_module working_memory kernel_working_memory)"
SELF_JSON="$(run_module self_model kernel_self_model)"
LEARNING_JSON="$(run_module learning_assimilation kernel_learning_assimilation)"
GOALS_JSON="$(run_module goal_stack kernel_goal_stack)"
CURIOSITY_JSON="$(run_module curiosity_queue kernel_curiosity_queue)"
OPENCORE_JSON="$(run_module opencore_supervision_bridge kernel_opencore_supervision_bridge)"
REFLECTION_JSON="$(run_module reflection kernel_reflection_layer)"

PERCEPTION_JSON="$PERCEPTION_JSON" \
ATTENTION_JSON="$ATTENTION_JSON" \
WORKING_JSON="$WORKING_JSON" \
SELF_JSON="$SELF_JSON" \
REFLECTION_JSON="$REFLECTION_JSON" \
LEARNING_JSON="$LEARNING_JSON" \
GOALS_JSON="$GOALS_JSON" \
CURIOSITY_JSON="$CURIOSITY_JSON" \
OPENCORE_JSON="$OPENCORE_JSON" \
TS="$TS" \
TICK_REG="$TICK_REG" \
TICK_LOG="$TICK_LOG" \
python3 - <<'PY'
import json, os, time
from pathlib import Path

def L(name):
    raw = os.environ.get(name) or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw[:400], "ok": False}

payload = {
    "module": "qsb_kernel_cognitive_tick",
    "timestamp_utc": os.environ["TS"],
    "purpose": ("Run perception, attention, working memory, self-model, "
                "reflection, learning assimilation, goal stack, curiosity "
                "queue, and OpenCore supervision in order. Advisory only."),
    "module_results": {
        "perception": L("PERCEPTION_JSON"),
        "attention": L("ATTENTION_JSON"),
        "working_memory": L("WORKING_JSON"),
        "self_model": L("SELF_JSON"),
        "reflection": L("REFLECTION_JSON"),
        "learning_assimilation": L("LEARNING_JSON"),
        "goal_stack": L("GOALS_JSON"),
        "curiosity_queue": L("CURIOSITY_JSON"),
        "opencore_supervision": L("OPENCORE_JSON"),
    },
    "registries_written": [
        "data/registries/qsb_kernel_perception_snapshot.json",
        "data/registries/qsb_kernel_attention_state.json",
        "data/registries/qsb_kernel_working_memory.json",
        "data/registries/qsb_kernel_self_model.json",
        "data/registries/qsb_kernel_reflection_state.json",
        "data/registries/qsb_kernel_learning_assimilation_state.json",
        "data/registries/qsb_kernel_goal_stack.json",
        "data/registries/qsb_kernel_curiosity_queue.json",
        "data/registries/qsb_kernel_opencore_supervision_state.json",
    ],
    "logs_appended": [
        "data/logs/qsb_kernel_reflection_loop.jsonl",
        "data/logs/qsb_kernel_learning_assimilation.jsonl",
        "data/logs/qsb_kernel_opencore_supervision.jsonl",
        "data/logs/qsb_kernel_cognitive_tick.jsonl",
    ],
    "safety": {
        "advisory_only": True,
        "execution_allowed": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "live_trading_enabled": False,
        "live_dispatch_enabled": False,
        "autonomous_workers_enabled": False,
        "real_order_execution_enabled": False,
        "binance_order_execution_enabled": False,
        "stock_order_execution_enabled": False,
        "web_access_autonomous_enabled": False,
        "maintenance_auto_repair_enabled": False,
    },
}

Path(os.environ["TICK_REG"]).write_text(
    json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

with open(os.environ["TICK_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "ts": payload["timestamp_utc"],
        "module_results_summary": {
            k: {"written": v.get("written"),
                "confidence": v.get("confidence")}
            for k, v in payload["module_results"].items()
            if isinstance(v, dict)
        },
        "execution_allowed": False,
    }, default=str) + "\n")

print(json.dumps({
    "ok": True,
    "wrote": os.environ["TICK_REG"],
    "modules_run": list(payload["module_results"].keys()),
    "timestamp_utc": payload["timestamp_utc"],
}, indent=2))
PY

echo "[cognitive_tick] done at $TS"
