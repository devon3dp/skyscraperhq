#!/bin/bash
# start_claude_hq_cli.sh — Claude HQ CLI continuity boot (Ross 2026-07-10).
# Loads the context a Claude HQ CLI session needs to continue coherently:
# identity, rulebook pointer, Task Council snapshot, latest report, R108/Gate 19,
# TP/Acer auth-guard state, Pi blocker, Tour Guide dependency, and the dashboard
# work queue. READ-ONLY: it prints context; it does not execute work.
set -u
ROOT=/vaults/nvme0/qsb_tower_v1
cd "$ROOT" || exit 1
SEND=/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT
echo "================ CLAUDE HQ CLI BOOT CONTEXT ================"
echo "ts: $(date -Is)   host: $(hostname)   root: $ROOT"
echo
echo "--- IDENTITY ---"
echo "  Claude HQ (hq_claude) — HQ CEO. Operates through :8850 dash + CLI."
echo "  MEMORY: /home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/MEMORY.md"
echo
echo "--- RULEBOOK (read on wake) ---"
ls -1 floors/floor_47*/rulebook_*.md 2>/dev/null | tail -1 || echo "  (rulebook pointer in MEMORY.md: R01-R93 + R108/Gate19)"
echo
echo "--- TASK COUNCIL SNAPSHOT (counts) ---"
python3 -c "
import sys;sys.path.insert(0,'tools');import qsb_council_tasks as q
s=q.snapshot();t=s['tasks']
act=[x for x in t if (x.get('state') or '').lower() in q.CAP_ACTIVE_STATES]
print('  total',len(t),'| active',len(act),'| open',sum(1 for x in t if x['state']=='open'))
" 2>/dev/null || echo "  (council read err)"
echo
echo "--- R108 / GATE 19 LIVENESS (last sweep) ---"
python3 tools/qsb_team_liveness_watchdog.py 2>/dev/null | tail -2 || echo "  (run watchdog for live sweep)"
echo
echo "--- TP/ACER AUTH-GUARD STATE ---"
echo "  sandbox worker runtime: tools/qsb_ceo_runtime_worker_sandbox.py (auth-guarded, NOT live-deployed)"
echo "  live TP :8861 / Acer :8862 = status-only runtimes (HQ-hosted, not physical CEOs)"
echo
echo "--- PI BLOCKER ---"
echo "  Receptionist Pi (Pi4 8GB): NetworkManager was crashing (Illegal instruction = corrupted card)."
echo "  Action: clean 64-bit reflash in progress / desktop-usable rebuild."
echo
echo "--- TOUR GUIDE DEPENDENCY ---"
echo "  Tour Guide dash :8854 live; TP/Acer build of it blocked until they are real workers."
echo
echo "--- DASHBOARD WORK QUEUE ---"
python3 tools/claude_hq_dashboard_work_backend.py list 2>/dev/null || echo "  (no queue yet)"
echo
echo "--- LATEST REPORT ---"
echo "  $SEND/LATEST_REPORT.txt"
head -3 "$SEND/LATEST_REPORT.txt" 2>/dev/null | sed 's/^/    /'
echo "==========================================================="
echo "Ready. Pending dashboard work: run"
echo "  python3 tools/claude_hq_dashboard_work_backend.py list"
