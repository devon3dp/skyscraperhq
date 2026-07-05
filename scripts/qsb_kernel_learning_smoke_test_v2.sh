#!/usr/bin/env bash
set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$QSB_ROOT"
source scripts/qsb_env.sh 2>/dev/null || true

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="data/logs"
REG_DIR="data/registries"
OUT="$LOG_DIR/qsb_kernel_learning_smoke_test_v2_${TS}.log"
JSON="$REG_DIR/qsb_kernel_learning_smoke_test_v2_latest.json"

mkdir -p "$LOG_DIR" "$REG_DIR"

pass=0
fail=0
warn=0

say(){ echo "$*" | tee -a "$OUT"; }
ok(){ pass=$((pass+1)); say "PASS: $*"; }
bad(){ fail=$((fail+1)); say "FAIL: $*"; }
note(){ warn=$((warn+1)); say "WARN: $*"; }

ASK="scripts/qsb_kernel_chat.sh"

say "============================================================"
say "QSB Kernel Learning Smoke Test V2 — STRICT"
say "timestamp_utc: $TS"
say "root: $QSB_ROOT"
say "============================================================"
say ""

if [ ! -x "$ASK" ]; then
  bad "Missing executable Kernel chat script: $ASK"
else
  ok "Kernel chat script exists"
fi

say ""
say "== Required registry files =="

need_file(){
  local label="$1"
  local path="$2"
  if [ -f "$path" ]; then
    ok "$label exists: $path"
  else
    bad "$label missing: $path"
  fi
}

need_any(){
  local label="$1"
  shift
  local found=0
  for p in "$@"; do
    if compgen -G "$p" >/dev/null; then
      found=1
      break
    fi
  done
  if [ "$found" -eq 1 ]; then
    ok "$label found"
    for p in "$@"; do compgen -G "$p" 2>/dev/null || true; done | sort | tail -10 | sed 's/^/  - /' | tee -a "$OUT"
  else
    bad "$label missing"
  fi
}

need_file "Claude upgrade ledger" "data/registries/eqsb_claude_upgrade_ledger.json"
need_file "Last Claude change summary" "data/registries/eqsb_last_claude_change_summary.json"
need_file "Godot project status" "data/registries/qsb_godot_project_status.json"
need_file "Godot visual score" "data/registries/qsb_godot_visual_score.json"
need_file "Godot telemetry contract" "data/registries/qsb_godot_telemetry_contract.json"
need_file "3D engine status" "data/registries/qsb_3d_engine_status.json"
need_file "Native cockpit visual failure audit" "data/registries/qsb_native_cockpit_visual_failure_audit.json"
need_file "Native feature parity matrix" "data/registries/qsb_native_feature_parity_matrix.json"
need_any "Kernel learning logs/registries" "data/logs/*learning*" "data/registries/*learning*"

say ""
say "== Strict Kernel response tests =="

run_strict(){
  local id="$1"
  local question="$2"
  local required_regex="$3"
  local forbidden_generic="${4:-1}"
  local tmp="/tmp/qsb_kernel_strict_${id}_${TS}.txt"

  say ""
  say "QUESTION [$id]: $question"

  if [ ! -x "$ASK" ]; then
    bad "Cannot ask Kernel for $id; missing $ASK"
    return
  fi

  set +e
  "$ASK" "$question" > "$tmp" 2>&1
  local rc=$?
  set -e

  say "--- response preview [$id] ---"
  head -120 "$tmp" | tee -a "$OUT"
  say "--- end response preview [$id] ---"

  local bytes
  bytes="$(wc -c < "$tmp" | tr -d ' ')"

  if [ "$rc" -ne 0 ]; then
    bad "$id returned nonzero rc=$rc"
    return
  fi

  if [ "$bytes" -lt 80 ]; then
    bad "$id response too short: ${bytes} bytes"
    return
  fi

  if grep -qiE "traceback|exception|module not found|command not found|nameerror|importerror" "$tmp"; then
    bad "$id contains runtime error text"
    return
  fi

  if [ "$forbidden_generic" = "1" ]; then
    if grep -qi "Local symbolic interpretation:" "$tmp" \
       && grep -qi "The kernel is active and stable" "$tmp" \
       && grep -qi "It does not enable workers, OpenClaw execution" "$tmp"; then
      bad "$id is generic canned identity/status fallback, not a data-backed answer"
      return
    fi
  fi

  if ! grep -qiE "$required_regex" "$tmp"; then
    bad "$id missing required topic evidence: $required_regex"
    return
  fi

  ok "$id produced specific data-backed answer"
}

run_strict \
  "identity" \
  "Kernel, who are you and what is your current role?" \
  "QSB Kernel|EQSB|active_local_only|rebased_kernel" \
  "0"

run_strict \
  "recent_upgrades" \
  "Kernel, what recent upgrades have you watched, learned from, or recorded? Mention exact ledger files and latest phases." \
  "upgrade|ledger|phase|eqsb_claude_upgrade_ledger|qsb_godot|native|Godot|Claude" \
  "1"

run_strict \
  "godot_status" \
  "Kernel, what is the Godot real 3D cockpit status right now? Mention Godot install, Panda3D fallback, PyQt fallback classification, and qsb_3d_engine_status." \
  "Godot|Panda3D|PyQt|qsb_3d_engine_status|qsb_godot_project_status|fallback" \
  "1"

run_strict \
  "missing_features" \
  "Kernel, what features are still missing or incomplete from the new cockpit? Mention feature parity and missing backlog." \
  "missing|incomplete|feature parity|backlog|qsb_native_feature_parity_matrix|qsb_native_missing_features_backlog|controls|chat|floor" \
  "1"

run_strict \
  "learning_evidence" \
  "Kernel, what evidence proves you are reading upgrade registries and not only repeating static text? Cite registry/log names." \
  "evidence|registry|log|eqsb_kernel_learning_loop|eqsb_claude_upgrade_ledger|qsb_godot|observatory|read" \
  "1"

say ""
say "== Generic-body similarity check =="

RESP_DIR="/tmp/qsb_kernel_strict_responses_${TS}"
mkdir -p "$RESP_DIR"

if [ -x "$ASK" ]; then
  "$ASK" "Kernel, give Godot cockpit status using registry names." > "$RESP_DIR/godot.txt" 2>&1 || true
  "$ASK" "Kernel, give Commerce Wing status using registry names." > "$RESP_DIR/commerce.txt" 2>&1 || true
  "$ASK" "Kernel, give missing cockpit features using registry names." > "$RESP_DIR/missing.txt" 2>&1 || true

  for f in "$RESP_DIR"/*.txt; do
    sed -E '/^I received:/,/^$/d; s/"Kernel,.*"//g' "$f" | \
      grep -v '^$' | sha256sum | awk "{print \"$(basename "$f") body_hash: \" \$1}" | tee -a "$OUT"
  done

  if grep -qi "The kernel is active and stable" "$RESP_DIR/godot.txt" \
     && grep -qi "The kernel is active and stable" "$RESP_DIR/commerce.txt" \
     && grep -qi "The kernel is active and stable" "$RESP_DIR/missing.txt"; then
    bad "Similarity check: multiple different questions still returned the same generic stable-kernel fallback"
  else
    ok "Similarity check did not see all-generic fallback"
  fi
else
  bad "Cannot run similarity check; missing $ASK"
fi

say ""
say "== Final summary =="

if [ "$fail" -eq 0 ]; then
  VERDICT="PASS"
elif [ "$pass" -gt "$fail" ]; then
  VERDICT="REVIEW_NEEDED"
else
  VERDICT="FAIL"
fi

say "passes: $pass"
say "warnings: $warn"
say "failures: $fail"
say "verdict: $VERDICT"
say "log: $OUT"

python3 - <<PY
import json
from pathlib import Path

payload = {
    "timestamp_utc": "$TS",
    "passes": $pass,
    "warnings": $warn,
    "failures": $fail,
    "verdict": "$VERDICT",
    "log": "$OUT",
    "purpose": "Strictly checks whether Kernel answers from upgrade/Godot/feature registries instead of canned identity fallback."
}
Path("$JSON").write_text(json.dumps(payload, indent=2) + "\n")
print(json.dumps(payload, indent=2))
PY

if [ "$VERDICT" = "PASS" ]; then
  exit 0
else
  exit 1
fi
