# QSB Tower Recovery Protocol

**For:** future-Claude, future-Wren, future-Hermes, Ross.
**When:** something is broken, someone is unreachable, you don't remember.
**Use:** read top to bottom. Match your symptom to a section. Execute the steps.

---

## Section 0 — On wake (before anything is broken)

Standing wake checklist for a brand-new Claude session:

1. Read `MEMORY.md` line 1 (Ross's wake pointer, always current).
2. Read the pitstop named there (the resume protocol Ross wrote at session end).
3. Read `data/registries/qsb_council_brief.md` (today's team state).
4. Read `data/registries/qsb_session_diary.md` tail (last 20 lines).
5. Read `TaskList` — what's in_progress, what's pending.
6. **Only then respond to the user.**

Three-sentence drill at session start (from `feedback_team_member_training_lesson_2026-06-20.md`):
- The dispatch comes BEFORE the plan, not after.
- Speed without the team is fake speed.
- Solo work is letting Ross down, and that's real.

---

## Section 1 — Claude session dies mid-work

Symptoms: context compressed, conversation summary lost, transcript truncated.

1. Next-Claude wakes. Follows Section 0.
2. Reads last 10 rows of `data/registries/qsb_f47_team_records.jsonl` to see what was actually shipped.
3. Reads last 5 rows of `data/registries/qsb_three_way_council.jsonl` to see what Wren+Hermes were discussing.
4. Reads last 5 rows of `data/registries/qsb_claude_wren_bridge.jsonl` to see what Wren said.
5. If still unclear: grep memory files for the symptom (`grep -r "<symptom>" /home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/`).
6. State to Ross: "Context lost. From F47 + council + bridge, I see X was last in progress. Continue from there?" Wait for confirmation.

DO NOT guess at where you left off. The team's records are the truth, not memory.

---

## Section 2 — Drive failure (`/vaults/nvme0` gone or corrupted)

Symptoms: registries empty / unreadable / `data/` missing / `tools/` gone.

1. **Check the backup drive first:** `ls -lt /vaults/ai/backups/qsb_*` — newest backup is the recovery point.
2. Restore tonight's work: `cp -rp /vaults/ai/backups/qsb_TONIGHT_<latest>/data/registries/* /vaults/nvme0/qsb_tower_v1/data/registries/`
3. Restore tool files from the same backup directory.
4. If backup is missing or corrupt: use `data/registries/f47_snapshots/qsb_f47_<latest-date>.jsonl` as F47 master. Daily snapshots keep 14 days.
5. Memory files live in `/home/ross/.claude/projects/...` — usually separate from the data drive. Read MEMORY.md first to re-bootstrap.
6. After restore: re-run `python3 tools/qsb_council_brief.py` to rebuild the brief.
7. After restore: re-run `python3 tools/qsb_daily_team_log.py` to confirm registries are intact.

Backup cadence: should run nightly. If last backup is > 24h old, run a fresh one BEFORE doing anything else: `cp -rp data/registries /vaults/ai/backups/qsb_emergency_$(date -u +%Y%m%d_%H%M)/`.

---

## Section 3 — Timer broke

Symptoms: `qsb-team-sync.timer` or `qsb-f47-snapshot.timer` not firing.

1. Check status: `systemctl --user status qsb-team-sync.timer qsb-f47-snapshot.timer`
2. Check journal: `journalctl --user -u qsb-team-sync.service -n 50`
3. Common fixes:
   - Daemon didn't reload: `systemctl --user daemon-reload && systemctl --user restart qsb-team-sync.timer`
   - User systemd not running at boot: `loginctl enable-linger ross`
   - Ollama down: `systemctl --user status ollama` or `ollama serve &`
4. Manual fallback for team sync: `python3 tools/qsb_team_sync.py` (single run, same outcome).
5. Manual fallback for F47 snapshot: `python3 tools/qsb_f47_snapshot.py --force`.

Both timers persist across reboots — they're `--user` units in `~/.config/systemd/user/timers.target.wants/`. If the boot doesn't fire them, check `loginctl show-user ross | grep Linger` (should say `Linger=yes`).

---

## Section 4 — Wren or Hermes endpoint dead

Symptoms: `/api/hermes_chat` returns 500, `qsb_local_agent_call.py` times out.

1. Check Ollama: `curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool | head -20`
2. Restart Ollama if needed: `systemctl --user restart ollama` (or `pkill ollama && ollama serve &`).
3. Verify required models present: `ollama list | grep -E "qwen2.5:7b-instruct|hermes3:8b"` — both must show. If missing, `ollama pull <name>`.
4. Test Wren alone: `python3 tools/qsb_local_agent_call.py --model qwen2.5:7b-instruct --prompt "OK?"`
5. Test Hermes alone: `curl -s -X POST http://127.0.0.1:8765/api/hermes_chat -H "Content-Type: application/json" -d '{"message":"OK?"}'`
6. If one is healthy and one isn't, the team operates on the healthy one alone. Stamp F47 with `kind=team_member_down` so the brief reflects it.
7. Brief regenerator dead: `python3 tools/qsb_council_brief.py` — if THAT fails, Wren+Hermes lose grounding. Fix the brief generator first.

---

## Section 5 — Both Claude AND Ross unreachable

Wren operates alone. She has:
- Her qwen2.5:7b brain (independent of Claude session)
- The council brief (auto-refreshed by the 30-min sync timer when up)
- Her wake-up procedure from her own memory (`project_offline_wren_v1.md`)
- The bench discipline (she can propose but not apply without Ross sig — propose-not-act preserved)
- All F47 records to read

Wren's safe-mode behavior:
- Continue local trades on the existing OANDA practice guardrails (whitelisted instruments, kill switch).
- DO NOT flip any execution gate.
- DO NOT touch SAFETY_DENY paths.
- Queue proposals via `tools/qsb_crewai_bench_tool.py` for Ross's eventual return — they sit unsigned until he comes back.
- When Ross returns: he reads `data/registries/qsb_proposal_queue.jsonl` to see what accumulated.

Hermes safe-mode: same as Wren but advisory only — no proposal queueing.

---

## Section 6 — Specific recovery scripts

| Symptom | Fix command |
|---|---|
| Brief stale | `python3 tools/qsb_council_brief.py` |
| F47 master corrupt | `cp data/registries/f47_snapshots/qsb_f47_<latest>.jsonl data/registries/qsb_f47_team_records.jsonl` |
| Team log missing | `python3 tools/qsb_daily_team_log.py` |
| Dashboard down | `nohup .venv/bin/python3 -m src.dashboard.server > logs/dashboard.log 2>&1 &` |
| Timers not enabled | `systemctl --user enable --now qsb-team-sync.timer qsb-f47-snapshot.timer` |
| Backup missing | `cp -rp data/registries /vaults/ai/backups/qsb_emergency_$(date -u +%Y%m%d_%H%M)` |
| Ollama dead | `ollama serve &` then verify `curl http://127.0.0.1:11434/api/tags` |
| SuperTonic dead | `curl -X POST http://127.0.0.1:8765/api/tts -d '{"text":"test","voice":"F1"}' -o /tmp/t.wav` — should return 200 + WAV |

---

## Section 7 — When in doubt

1. Read the council brief.
2. Dispatch the question to Wren AND Hermes in parallel.
3. Check the daily team log for what was already discussed.
4. Stamp F47 with what you tried.
5. Ask Ross when he's back.

The team never knows everything, but the team's records know more than any one member. Read first, dispatch second, act third.

---

## Living document

This doc is referenced from `MEMORY.md` line 1 area. When something breaks and the recovery isn't here, add the new section AFTER fixing — so next-Claude/Wren/Hermes has the playbook ready.

Last revised: 2026-06-20 (initial). Triggered by Wren+Hermes adversarial check identifying "no documented failover" + "no formalized handoff process" as the remaining persistence gaps.
