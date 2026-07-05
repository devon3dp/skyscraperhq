#!/usr/bin/env bash
# qsb_dashboard_and_trader_status_sweep.sh — direct truthful sweep of dashboard, traders, brokers.
# Writes data/registries/qsb_dashboard_and_trader_status_latest.json + data/logs/qsb_dashboard_and_trader_status_report.md

set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OUT_JSON=data/registries/qsb_dashboard_and_trader_status_latest.json
OUT_MD=data/logs/qsb_dashboard_and_trader_status_report.md
mkdir -p data/registries data/logs

# Use the SAFE ps pattern (memory: project_2026-06-26_fleet_dead_false_positive)
n_traders=$(ps -eo cmd ww | awk '/python3/ && /qsb_belief_driven_trader/ {n++} END {print n+0}')
n_ensembles=$(ps -eo cmd ww | awk '/python3/ && /qsb_ensemble_coordinator/ {n++} END {print n+0}')
n_bus=$(ps -eo cmd ww | awk '/python3/ && /qsb_event_bus\.py/ {n++} END {print n+0}')
n_belief=$(ps -eo cmd ww | awk '/python3/ && /qsb_belief_updater/ {n++} END {print n+0}')
n_regime=$(ps -eo cmd ww | awk '/python3/ && /qsb_regime_detector/ {n++} END {print n+0}')
n_streams=$(ps -eo cmd ww | awk '/python3/ && /qsb_f4[123]_(binance|oanda|alpaca)_stream/ {n++} END {print n+0}')

dash_8847=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8847/ 2>/dev/null || echo 000)
dash_8849=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8849/ 2>/dev/null || echo 000)
dash_8848=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8848/ 2>/dev/null || echo 000)

# Editor + plugin
editor_pid=$(pgrep -f 'UnrealEditor.*QSB_Skyscraper.uproject' | head -1 || true)
tcp_55557=$(ss -tnlp 2>/dev/null | grep -c ':55557 ')
live_pulse_pid=$(pgrep -f 'qsb_ue5_live_pulse.py' | head -1 || true)

# Vault — Alpaca config
alpaca_env_present="no"
[[ -f floors/floor_28_security_department/vault/.env.alpaca ]] && alpaca_env_present="yes"
[[ -f floors/floor_28_security_department/vault/.env.alpaca.paper ]] && alpaca_env_present="yes(paper)"
oanda_env_present="no"
[[ -f floors/floor_28_security_department/vault/.env.oanda ]] && oanda_env_present="yes"
[[ -f floors/floor_28_security_department/vault/.env.oanda.practice ]] && oanda_env_present="yes(practice)"
binance_env_present="no"
[[ -f floors/floor_28_security_department/vault/.env.binance ]] && binance_env_present="yes"
[[ -f floors/floor_28_security_department/vault/.env.binance.testnet ]] && binance_env_present="yes(testnet)"

# Pot / journal freshness
pot_path=data/registries/qsb_portfolio_pot.json
pot_age_s="unknown"; pot_open=0; pot_committed="0"
if [[ -f "$pot_path" ]]; then
  pot_age_s=$(($(date -u +%s) - $(stat -c %Y "$pot_path")))
  pot_open=$(jq '.open_positions | length' "$pot_path" 2>/dev/null || echo 0)
  pot_committed=$(jq '.committed_gbp' "$pot_path" 2>/dev/null || echo 0)
fi

# Trader log activity (any trader producing OPEN/CLOSE events in the last 5 min?)
recent_open=$(find logs/intelligence -name 'trader_*.log' -mmin -5 2>/dev/null | head -1)
trader_activity_5m="quiet"
[[ -n "$recent_open" ]] && trader_activity_5m="active(latest=$(basename "$recent_open"))"

# Bus journal freshness
bus_j=data/registries/qsb_bus_journal.jsonl
bus_j_age_s="unknown"
[[ -f "$bus_j" ]] && bus_j_age_s=$(($(date -u +%s) - $(stat -c %Y "$bus_j")))

# OANDA broker truth (memory: tracker_vs_broker_truth — call broker direct if creds present)
oanda_realized_today="not_checked"
if [[ "$oanda_env_present" == "yes(practice)" ]] && [[ -x .venv/bin/python3 ]]; then
  # Don't actually call broker here — that's a separate tool. Surface what we know via the snapshot.
  if [[ -f data/registries/qsb_oanda_snapshot.json ]]; then
    oanda_realized_today=$(jq -r '.realized_today_gbp // "unknown"' data/registries/qsb_oanda_snapshot.json 2>/dev/null || echo unknown)
  fi
fi

cat > "$OUT_JSON" <<EOF
{
  "ts": "${TS_UTC}",
  "fleet": {
    "belief_traders_alive": ${n_traders},
    "ensembles_alive": ${n_ensembles},
    "bus_processes": ${n_bus},
    "belief_updater_processes": ${n_belief},
    "regime_detector_processes": ${n_regime},
    "stream_clients": ${n_streams}
  },
  "dashboards": {
    "qsb_traders_live_serve_8847": "${dash_8847}",
    "qsb_studio_serve_8849": "${dash_8849}",
    "lumen_8848": "${dash_8848}"
  },
  "unreal": {
    "editor_pid": "${editor_pid:-none}",
    "tcp_55557_listening": ${tcp_55557},
    "live_pulse_pid": "${live_pulse_pid:-none}"
  },
  "vault_creds_present": {
    "alpaca": "${alpaca_env_present}",
    "oanda": "${oanda_env_present}",
    "binance": "${binance_env_present}"
  },
  "pot": {
    "open_positions": ${pot_open:-0},
    "committed_gbp": ${pot_committed},
    "json_age_seconds": ${pot_age_s}
  },
  "trader_activity_5m": "${trader_activity_5m}",
  "bus_journal_age_seconds": ${bus_j_age_s},
  "oanda_realized_today_gbp_from_snapshot": "${oanda_realized_today}"
}
EOF

cat > "$OUT_MD" <<EOF
# Dashboard + Trader Status Sweep — ${TS_UTC}

## Headline

- Dashboard 8847 (traders_live): **${dash_8847}**
- Dashboard 8849 (studio):       **${dash_8849}**
- UE editor:                     ${editor_pid:+pid ${editor_pid} alive}${editor_pid:-DOWN}
- TCP 55557 (plugin):            $( [[ ${tcp_55557} -gt 0 ]] && echo LISTENING || echo down )
- Fleet:                         ${n_traders} belief traders + ${n_ensembles} ensembles + bus×${n_bus}, belief×${n_belief}, regime×${n_regime}, streams×${n_streams}

## Brokers

- Alpaca creds:   ${alpaca_env_present}
- OANDA creds:    ${oanda_env_present}
- Binance creds:  ${binance_env_present}

## Pot

- Open positions: ${pot_open:-0}
- Committed:      £${pot_committed}
- JSON age:       ${pot_age_s}s

## Verdict (be direct)

- **Dashboards 8847/8849:** $( [[ "$dash_8847" == "200" && "$dash_8849" == "200" ]] && echo WORKING || echo PARTIAL/BROKEN )
- **Unreal visible build:** $( [[ -n "$editor_pid" && "$tcp_55557" -gt 0 ]] && echo WORKING || echo BROKEN )
- **Trader activity in last 5m:** ${trader_activity_5m}
- **Bus journal age:** ${bus_j_age_s}s
- **Paper trading active:** $( [[ ${n_traders} -gt 0 && "${pot_age_s}" != "unknown" && ${pot_age_s} -lt 600 ]] && echo YES || echo UNCLEAR )

Files proving status:
- ${pot_path}
- ${bus_j}
- data/registries/qsb_oanda_snapshot.json (if present)
- logs/intelligence/trader_*.log (most recent trader logs)
EOF

echo "wrote: $OUT_JSON"
echo "wrote: $OUT_MD"
cat "$OUT_JSON"
