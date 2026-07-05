#!/data/data/com.termux/files/usr/bin/bash
# qsb_galaxy_receptionist_supervisor.sh — QSB Tower V1.5 / Galaxy phone
# Lineage: Floor 12 Reception, supervised on-device under Termux.
# Safety stance: PID-watch + restart ONLY. Does not decide tower business.
# Does not call providers, does not flip gates, does not parse call content.

set -u

: "${RECEPTIONIST_CMD:=$HOME/qsb_galaxy_receptionist.sh}"
: "${IRIS_LOG:=$HOME/iris.log}"
: "${SUP_DIR:=$HOME/skyscraperhqphone}"
: "${SUP_LOG:=$SUP_DIR/qsb_receptionist_supervisor.log}"
: "${HEALTH_LOG:=$SUP_DIR/qsb_receptionist_health.jsonl}"
: "${CHECK_INTERVAL:=30}"
: "${STALE_THRESHOLD:=180}"
: "${CRASH_WINDOW_SEC:=600}"
: "${CRASH_THRESHOLD:=3}"

declare -a CRASH_TS=()
LAST_RESTART_TS=""

now_iso() { date -u +%FT%TZ 2>/dev/null || echo "1970-01-01T00:00:00Z"; }
now_epoch() { date -u +%s 2>/dev/null || echo 0; }

ensure_dir() {
  [ -d "$SUP_DIR" ] || mkdir -p "$SUP_DIR" 2>/dev/null || return 1
  return 0
}

log_row() {
  local event="$1"
  local extra="${2:-}"
  local ts
  ts="$(now_iso)"
  local line
  if [ -n "$extra" ]; then
    line="{\"ts\":\"$ts\",\"event\":\"$event\",$extra}"
  else
    line="{\"ts\":\"$ts\",\"event\":\"$event\"}"
  fi
  ensure_dir || { echo "$line" >&2; return 0; }
  echo "$line" >> "$SUP_LOG" 2>/dev/null || echo "$line" >&2
}

health_row() {
  local payload="$1"
  ensure_dir || { echo "$payload" >&2; return 0; }
  echo "$payload" >> "$HEALTH_LOG" 2>/dev/null || echo "$payload" >&2
}

receptionist_pid() {
  pgrep -f "qsb_galaxy_receptionist.sh" 2>/dev/null | head -n1 || true
}

iris_age_sec() {
  if [ ! -f "$IRIS_LOG" ]; then echo 999999; return 0; fi
  local m n
  m=$(date -u -r "$IRIS_LOG" +%s 2>/dev/null || echo 0)
  n=$(now_epoch)
  echo $(( n - m ))
}

prune_crash_window() {
  local cutoff="$1"
  local kept=()
  local t
  for t in "${CRASH_TS[@]:-}"; do
    [ -z "$t" ] && continue
    [ "$t" -ge "$cutoff" ] && kept+=("$t")
  done
  CRASH_TS=("${kept[@]:-}")
}

start_receptionist() {
  local restart_ts_iso restart_ts_epoch
  restart_ts_iso="$(now_iso)"
  restart_ts_epoch="$(now_epoch)"
  log_row "down_detected" "\"prev_restart\":\"$LAST_RESTART_TS\""
  nohup bash "$RECEPTIONIST_CMD" > "$IRIS_LOG" 2>&1 &
  disown 2>/dev/null || true
  sleep 3
  local new_pid
  new_pid="$(receptionist_pid)"
  if [ -n "$new_pid" ]; then
    LAST_RESTART_TS="$restart_ts_iso"
    CRASH_TS+=("$restart_ts_epoch")
    log_row "restarted" "\"pid\":\"$new_pid\",\"restart_ts\":\"$restart_ts_iso\""
  else
    log_row "restart_failed" "\"restart_ts\":\"$restart_ts_iso\""
  fi
}

escalate() {
  local n="$1"
  local reason="$2"
  local ts
  ts="$(now_iso)"
  local payload
  payload="{\"ts\":\"$ts\",\"state\":\"escalated\",\"crashes_in_window\":$n,\"last_restart_ts\":\"$LAST_RESTART_TS\",\"reason\":\"$reason\"}"
  health_row "$payload"
  log_row "escalated" "\"crashes_in_window\":$n,\"reason\":\"$reason\""
}

shutdown_handler() {
  log_row "supervisor_shutdown" "\"reason\":\"SIGTERM\""
  exit 0
}
trap shutdown_handler TERM INT

log_row "supervisor_started" "\"cmd\":\"$RECEPTIONIST_CMD\",\"interval\":$CHECK_INTERVAL"

while true; do
  pid="$(receptionist_pid)"
  age="$(iris_age_sec)"

  if [ -z "$pid" ]; then
    start_receptionist
  else
    log_row "check_ok" "\"pid\":\"$pid\",\"iris_age_sec\":$age"
    if [ "$age" -gt "$STALE_THRESHOLD" ]; then
      log_row "iris_stale_warn" "\"pid\":\"$pid\",\"iris_age_sec\":$age,\"note\":\"may be idle, may be mid-call\""
    fi
  fi

  cutoff=$(( $(now_epoch) - CRASH_WINDOW_SEC ))
  prune_crash_window "$cutoff"
  n_crashes="${#CRASH_TS[@]}"
  if [ "$n_crashes" -ge "$CRASH_THRESHOLD" ]; then
    escalate "$n_crashes" "crash_threshold_${CRASH_THRESHOLD}_in_${CRASH_WINDOW_SEC}s"
    CRASH_TS=()
  fi

  sleep "$CHECK_INTERVAL" || true
done
