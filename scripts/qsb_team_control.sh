#!/usr/bin/env bash
# Master command menu for the persistent QSB team system.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
CMD="${1:-help}"
shift || true

case "$CMD" in
  roster)        exec ./scripts/qsb_team_model_roster_probe.sh ;;
  memory)        exec ./scripts/qsb_team_memory_status.sh ;;
  brief)         exec ./scripts/qsb_team_build_shared_project_brief.sh ;;
  tick)          exec ./scripts/qsb_team_tick.sh ;;
  status)        exec ./scripts/qsb_team_status.sh ;;
  roundtable)    exec ./scripts/qsb_team_roundtable.sh "${1:-status check}" ;;
  unreal)        exec ./scripts/qsb_team_unreal_build_roundtable.sh "${@:-}" ;;
  wren)          exec ./scripts/qsb_wren_second_in_command_tick.sh ;;
  learn)         exec ./scripts/qsb_team_learning_tick.sh ;;
  prove)         exec ./scripts/qsb_team_prove_full_system.sh ;;
  daemon-start)  exec ./scripts/qsb_team_daemon_start.sh ;;
  daemon-status) exec ./scripts/qsb_team_daemon_status.sh ;;
  daemon-stop)   exec ./scripts/qsb_team_daemon_stop.sh ;;
  evolution)     exec ./scripts/qsb_team_evolution_review.sh ;;
  ask-wren)      exec ./scripts/team_adapters/qsb_ask_wren.sh "${1:-status}" ;;
  ask-hermes)    exec ./scripts/team_adapters/qsb_ask_hermes.sh "${1:-status}" ;;
  ask-iquest)    exec ./scripts/team_adapters/qsb_ask_iquest_coder.sh "${1:-status}" ;;
  help|--help|-h|*)
    cat <<EOF
QSB Team Control — master command menu

Usage: ./scripts/qsb_team_control.sh <command> [args]

Commands:
  roster         detect available team models
  memory         show team_memory layout + per-member file counts
  brief          (re)build the shared project brief
  tick           one team tick (roster + brief + Wren SIC + dashboards)
  status         compact team status (roster, recent calls, consensus, Wren, daemon)
  roundtable "TASK"  run a 3-reviewer roundtable on TASK
  unreal [obj]   team roundtable on a UE build objective + driver check
  wren           Wren SIC continuity tick
  ask-wren "Q"   one-shot ask Wren
  ask-hermes "Q" one-shot ask Hermes
  ask-iquest "Q" one-shot ask iQuest Coder
  learn          run learning tick (extract lessons from recent calls)
  evolution      compose evolution-review report
  prove          run full proof suite
  daemon-start   start background team-tick loop (default 30 min)
  daemon-status  is the daemon running?
  daemon-stop    stop the daemon
EOF
    ;;
esac
