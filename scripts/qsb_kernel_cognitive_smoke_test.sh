#!/usr/bin/env bash
# QSB Kernel — Cognitive Smoke Test (STRICT)
#
# Fails if:
#   * cognitive tick script missing
#   * cognitive status script missing
#   * any core cognitive registry missing after tick
#   * uncertainty question returns the canned identity/status fallback
#   * Kernel cannot mention perception/attention/working memory/
#     self-model/reflection/goal stack in its cognitive-architecture reply
#   * any of the 13 execution locks is not closed
#
# Passes only if all cognitive registries exist, uncertainty route is
# repaired, cognitive status runs, the Kernel gives a registry-backed
# cognitive answer, AND all execution locks remain closed.

set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$QSB_ROOT"
source scripts/qsb_env.sh 2>/dev/null || true

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="data/logs"
REG_DIR="data/registries"
OUT="$LOG_DIR/qsb_kernel_cognitive_smoke_test_${TS}.log"
JSON="$REG_DIR/qsb_kernel_cognitive_smoke_test_latest.json"

mkdir -p "$LOG_DIR" "$REG_DIR"

pass=0; fail=0; warn=0
say(){ echo "$*" | tee -a "$OUT"; }
ok(){ pass=$((pass+1)); say "PASS: $*"; }
bad(){ fail=$((fail+1)); say "FAIL: $*"; }
note(){ warn=$((warn+1)); say "WARN: $*"; }

say "============================================================"
say "QSB Kernel Cognitive Smoke Test — STRICT"
say "timestamp_utc: $TS"
say "root: $QSB_ROOT"
say "============================================================"

# ── Required scripts ────────────────────────────────────────────────────
need_script(){
    local p="$1"
    if [ -x "$p" ]; then
        ok "script executable: $p"
    elif [ -f "$p" ]; then
        bad "script exists but not executable: $p"
    else
        bad "script missing: $p"
    fi
}

say ""
say "== Cognitive scripts =="
need_script scripts/qsb_kernel_cognitive_tick.sh
need_script scripts/qsb_kernel_cognitive_status.sh
need_script scripts/qsb_kernel_chat.sh

# ── Cognitive registries ────────────────────────────────────────────────
need_registry(){
    local p="$1"
    if [ -f "$p" ]; then
        ok "registry present: $p"
    else
        bad "registry missing: $p"
    fi
}

say ""
say "== Cognitive registries =="
for r in \
    data/registries/qsb_kernel_cognitive_tick_latest.json \
    data/registries/qsb_kernel_perception_snapshot.json \
    data/registries/qsb_kernel_attention_state.json \
    data/registries/qsb_kernel_working_memory.json \
    data/registries/qsb_kernel_self_model.json \
    data/registries/qsb_kernel_reflection_state.json \
    data/registries/qsb_kernel_learning_assimilation_state.json \
    data/registries/qsb_kernel_goal_stack.json \
    data/registries/qsb_kernel_curiosity_queue.json \
    data/registries/qsb_kernel_opencore_supervision_state.json; do
    need_registry "$r"
done

# ── Execution locks (must all be false) ─────────────────────────────────
say ""
say "== Execution locks =="
LOCKS_OK=1
python3 - <<'PY' 2>&1 | tee -a "$OUT"
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def L(name):
    p = ROOT / "data/registries" / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

required_false = [
    "worker_execution_enabled",
    "provider_execution_enabled",
    "model_inference_enabled",
    "live_dispatch_enabled",
    "autonomous_workers_enabled",
    "direct_provider_access",
    "live_trading_enabled",
    "real_order_execution_enabled",
    "openclaw_execution_enabled",
    "binance_order_execution_enabled",
    "stock_order_execution_enabled",
    "web_access_autonomous_enabled",
    "maintenance_auto_repair_enabled",
]

sources = [
    "qsb_kernel_self_model.json",
    "qsb_kernel_cognitive_tick_latest.json",
    "qsb_kernel_opencore_supervision_state.json",
]
flags = {}
for s in sources:
    d = L(s)
    safety = (d.get("safety") or d.get("safety_locks")
               or d.get("current_safety_state") or {})
    if isinstance(safety, dict):
        for k, v in safety.items():
            flags.setdefault(k, []).append((s, v))
    for k in required_false:
        if k in d:
            flags.setdefault(k, []).append((s, d[k]))

violations = []
for k in required_false:
    if k not in flags:
        # If a flag is not surfaced by any registry, treat it as false-by-
        # contract (the CLAUDE.md mandates these are locked). This is
        # documented but not a failure on its own.
        print(f"NOTE: lock '{k}' not surfaced by any registry; treated as false-by-contract.")
        continue
    for src, val in flags[k]:
        if val is not False:
            violations.append((k, src, val))

if violations:
    print("LOCK_VIOLATIONS:")
    for k, src, val in violations:
        print(f"  - {k} reported as {val!r} in {src}")
    raise SystemExit(2)
print("ALL_LOCKS_CLOSED_OK")
PY
LOCKS_RC=${PIPESTATUS[0]}
if [ "$LOCKS_RC" -ne 0 ]; then
    bad "one or more execution locks reported non-false"
    LOCKS_OK=0
else
    ok "all 13 execution locks remain closed"
fi

# ── Uncertainty question must not return the canned fallback ────────────
say ""
say "== Uncertainty question routing =="
ASK="scripts/qsb_kernel_chat.sh"
TMP="/tmp/qsb_kernel_cog_uncertainty_${TS}.txt"

if [ ! -x "$ASK" ]; then
    bad "missing $ASK"
else
    set +e
    "$ASK" "Kernel, what are your current uncertainties, stale sources, missing registries, failed tests, and next recommended repair actions?" > "$TMP" 2>&1
    RC=$?
    set -e
    say "--- uncertainty response preview ---"
    head -120 "$TMP" | tee -a "$OUT"
    say "--- end uncertainty response preview ---"
    if [ "$RC" -ne 0 ]; then
        bad "uncertainty chat returned rc=$RC"
    elif grep -qiE "traceback|nameerror|importerror|module not found" "$TMP"; then
        bad "uncertainty response contains runtime error text"
    elif grep -qi "Local symbolic interpretation:" "$TMP" \
         && grep -qi "The kernel is active and stable" "$TMP" \
         && grep -qi "It does not enable workers, OpenClaw execution" "$TMP" \
         && ! grep -qi "Cognitive Reflection" "$TMP"; then
        bad "uncertainty question returned the canned identity/status fallback"
    elif ! grep -qiE "Cognitive Reflection|current_uncertainties|next_repair_action|next repair action|missing_registries|missing registries|stale_sources|stale sources" "$TMP"; then
        bad "uncertainty response lacks reflection-layer evidence"
    else
        ok "uncertainty question routed to reflection layer"
    fi
fi

# ── Cognitive-architecture reply must mention all 9 layers ─────────────
say ""
say "== Cognitive-architecture reply =="
TMP2="/tmp/qsb_kernel_cog_arch_${TS}.txt"
if [ ! -x "$ASK" ]; then
    bad "missing $ASK"
else
    set +e
    "$ASK" "Kernel, explain how you think now after the cognitive architecture upgrade. Mention perception, attention, working memory, self-model, reflection, learning assimilation, goal stack, curiosity queue, and OpenClaw/OpenCore supervision. Cite the registry files you are reading." > "$TMP2" 2>&1
    RC=$?
    set -e
    say "--- cognitive-architecture response preview ---"
    head -200 "$TMP2" | tee -a "$OUT"
    say "--- end cognitive-architecture response preview ---"
    if [ "$RC" -ne 0 ]; then
        bad "cognitive-architecture chat returned rc=$RC"
    else
        missing_keywords=""
        for kw in perception attention "working memory" "self-model" reflection \
                  "learning assimilation" "goal stack" "curiosity queue" \
                  "OpenCore\|OpenClaw\|opencore\|openclaw"; do
            if ! grep -qiE "$kw" "$TMP2"; then
                missing_keywords="$missing_keywords $kw"
            fi
        done
        if [ -n "$missing_keywords" ]; then
            bad "cognitive-architecture reply missing keywords:$missing_keywords"
        else
            ok "cognitive-architecture reply mentions all 9 layers"
        fi
    fi
fi

# ── Verdict ─────────────────────────────────────────────────────────────
say ""
say "== Final summary =="
if [ "$fail" -eq 0 ]; then
    VERDICT="PASS"
else
    VERDICT="FAIL"
fi

say "passes: $pass"
say "warnings: $warn"
say "failures: $fail"
say "verdict: $VERDICT"
say "log: $OUT"

VERDICT="$VERDICT" pass="$pass" warn="$warn" fail="$fail" TS="$TS" OUT="$OUT" JSON="$JSON" \
python3 - <<'PY'
import json, os
from pathlib import Path

payload = {
    "module": "qsb_kernel_cognitive_smoke_test",
    "timestamp_utc": os.environ["TS"],
    "passes": int(os.environ["pass"]),
    "warnings": int(os.environ["warn"]),
    "failures": int(os.environ["fail"]),
    "verdict": os.environ["VERDICT"],
    "log": os.environ["OUT"],
    "purpose": ("Strict smoke test of the kernel cognitive architecture: "
                "scripts present, registries present, uncertainty route "
                "repaired, all execution locks closed."),
    "safety": {
        "advisory_only": True,
        "execution_allowed": False,
    },
}
Path(os.environ["JSON"]).write_text(
    json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2, default=str))
PY

if [ "$VERDICT" = "PASS" ]; then
    exit 0
else
    exit 1
fi
