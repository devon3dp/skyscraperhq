#!/usr/bin/env bash
set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$QSB_ROOT"

source scripts/qsb_env.sh 2>/dev/null || true

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="data/logs"
REG_DIR="data/registries"
OUT="$LOG_DIR/qsb_kernel_learning_smoke_test_${TS}.log"
JSON="$REG_DIR/qsb_kernel_learning_smoke_test_latest.json"

mkdir -p "$LOG_DIR" "$REG_DIR"

pass=0
fail=0
warn=0

say() {
  echo "$*" | tee -a "$OUT"
}

ok() {
  pass=$((pass+1))
  say "PASS: $*"
}

bad() {
  fail=$((fail+1))
  say "FAIL: $*"
}

note() {
  warn=$((warn+1))
  say "WARN: $*"
}

say "============================================================"
say "QSB Kernel Learning / Upgrade Awareness Smoke Test"
say "timestamp_utc: $TS"
say "root: $QSB_ROOT"
say "============================================================"
say ""

say "== 1. Core script checks =="

if [ -x scripts/qsb_kernel_chat.sh ]; then
  ok "Kernel chat script exists: scripts/qsb_kernel_chat.sh"
else
  bad "Kernel chat script missing or not executable: scripts/qsb_kernel_chat.sh"
fi

if [ -x scripts/qsb_env.sh ]; then
  ok "QSB environment script exists: scripts/qsb_env.sh"
else
  note "qsb_env.sh not executable or missing; environment was sourced only if available"
fi

say ""
say "== 2. Registry / learning / upgrade artifact checks =="

check_glob() {
  local label="$1"
  local pattern="$2"
  local count
  count="$(find data -type f -iname "$pattern" 2>/dev/null | wc -l | tr -d ' ')"

  if [ "$count" -gt 0 ]; then
    ok "$label found ($count files)"
    find data -type f -iname "$pattern" 2>/dev/null | sort | tail -10 | sed 's/^/  - /' | tee -a "$OUT"
  else
    bad "$label missing: $pattern"
  fi
}

check_glob "Claude/change/upgrade records" "*claude*"
check_glob "Upgrade records" "*upgrade*"
check_glob "Learning records" "*learning*"
check_glob "Kernel records" "*kernel*"
check_glob "Native cockpit records" "*native*"
check_glob "Godot records" "*godot*"
check_glob "Observatory records" "*observatory*"

say ""
say "== 3. Recent activity check =="

RECENT_COUNT="$(find data/registries data/logs -type f -mtime -2 2>/dev/null | wc -l | tr -d ' ')"
if [ "$RECENT_COUNT" -gt 0 ]; then
  ok "Recent registry/log activity found in last 48 hours: $RECENT_COUNT files"
  find data/registries data/logs -type f -mtime -2 2>/dev/null \
    -printf "%TY-%Tm-%Td %TH:%TM %p\n" | sort | tail -30 | tee -a "$OUT"
else
  bad "No recent registry/log activity found in last 48 hours"
fi

say ""
say "== 4. Known status files =="

check_file() {
  local label="$1"
  local path="$2"
  if [ -f "$path" ]; then
    ok "$label exists: $path"
  else
    note "$label not found: $path"
  fi
}

check_file "3D engine status" "data/registries/qsb_3d_engine_status.json"
check_file "Native cockpit status" "data/registries/qsb_native_cockpit_status.json"
check_file "Godot project status" "data/registries/qsb_godot_project_status.json"
check_file "Godot visual score" "data/registries/qsb_godot_visual_score.json"
check_file "Native feature parity matrix" "data/registries/qsb_native_feature_parity_matrix.json"
check_file "Dashboard feature parity matrix" "data/registries/qsb_dashboard_feature_parity_matrix.json"
check_file "New 1000 workers record" "data/registries/qsb_new_1000_workers_employed.json"
check_file "Commerce wing masterplan" "data/registries/qsb_commerce_wing_masterplan.json"

say ""
say "== 5. Kernel chat question tests =="

ASK="scripts/qsb_kernel_chat.sh"

run_question() {
  local id="$1"
  local question="$2"
  local tmp="/tmp/qsb_kernel_learning_${id}_${TS}.txt"

  say ""
  say "QUESTION [$id]: $question"

  if [ ! -x "$ASK" ]; then
    bad "Cannot ask Kernel; missing $ASK"
    return
  fi

  set +e
  "$ASK" "$question" > "$tmp" 2>&1
  local rc=$?
  set -e

  local bytes
  bytes="$(wc -c < "$tmp" | tr -d ' ')"

  say "--- response preview [$id] ---"
  head -80 "$tmp" | tee -a "$OUT"
  say "--- end response preview [$id] ---"

  if [ "$rc" -ne 0 ]; then
    bad "Kernel chat command returned nonzero for $id: rc=$rc"
    return
  fi

  if [ "$bytes" -lt 60 ]; then
    bad "Kernel response too short for $id: ${bytes} bytes"
    return
  fi

  if grep -qiE "traceback|exception|error:|module not found|command not found" "$tmp"; then
    bad "Kernel response contains error text for $id"
    return
  fi

  if ! echo "$question" | grep -qiE "who are you|identity"; then
    if grep -qiE "I am QSB Kernel.*active_local_only.*execution locks|I am QSB Kernel.*OpenClaw.*providers" "$tmp"; then
      bad "Likely canned identity reply for non-identity question: $id"
      return
    fi
  fi

  ok "Kernel answered $id with non-error, non-empty response (${bytes} bytes)"
}

run_question "identity" "Kernel, who are you and what is your current role?"
run_question "recent_upgrades" "Kernel, what recent upgrades have you watched, learned from, or recorded?"
run_question "claude_changes" "Kernel, what did Claude change most recently in the dashboard or native cockpit?"
run_question "godot_status" "Kernel, what is the Godot/native 3D cockpit status right now?"
run_question "missing_features" "Kernel, what features are still missing or incomplete from the new cockpit?"
run_question "learning_evidence" "Kernel, what evidence proves you are reading upgrade registries and not only repeating static text?"

say ""
say "== 6. Response uniqueness check =="

RESP_DIR="/tmp/qsb_kernel_learning_responses_${TS}"
mkdir -p "$RESP_DIR"

if [ -x "$ASK" ]; then
  "$ASK" "Kernel, what is the Godot cockpit status?" > "$RESP_DIR/a.txt" 2>&1 || true
  "$ASK" "Kernel, what is the Commerce Wing status?" > "$RESP_DIR/b.txt" 2>&1 || true
  "$ASK" "Kernel, what are the missing dashboard features?" > "$RESP_DIR/c.txt" 2>&1 || true

  HASH_A="$(sha256sum "$RESP_DIR/a.txt" | awk '{print $1}')"
  HASH_B="$(sha256sum "$RESP_DIR/b.txt" | awk '{print $1}')"
  HASH_C="$(sha256sum "$RESP_DIR/c.txt" | awk '{print $1}')"

  say "hash_godot:   $HASH_A"
  say "hash_commerce:$HASH_B"
  say "hash_missing: $HASH_C"

  if [ "$HASH_A" = "$HASH_B" ] || [ "$HASH_A" = "$HASH_C" ] || [ "$HASH_B" = "$HASH_C" ]; then
    bad "Kernel gave duplicate identical responses to different questions"
  else
    ok "Kernel responses differ across different questions"
  fi
else
  bad "Cannot run uniqueness check; missing $ASK"
fi

say ""
say "== 7. Final summary =="

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
    "purpose": "Smoke test whether Kernel is watching, learning from, and answering based on upgrade/registry/system changes.",
}
Path("$JSON").write_text(json.dumps(payload, indent=2) + "\n")
print(json.dumps(payload, indent=2))
PY

say ""
say "Latest JSON summary: $JSON"

if [ "$VERDICT" = "PASS" ]; then
  exit 0
else
  exit 1
fi
