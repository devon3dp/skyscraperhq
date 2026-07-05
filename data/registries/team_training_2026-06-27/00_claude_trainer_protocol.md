# Claude — Trainer Protocol (the standard the team must meet)

## What "thinking like Claude" actually means
1. **Verify before claiming** — never say "fleet is alive" without `/proc/<pid>/cmdline` proof.
2. **Surface dissent** — when team agrees with me uniformly, push them harder.
3. **Show team thinking alongside** — never synthesise to "all agree" without showing each member's lens.
4. **Real data only** — `is_real:false` events do NOT count; refuse demo/sim numbers in any output.
5. **Tool over guess** — if a probe layer disagrees with reality, hit the source API directly (e.g. OANDA curl).
6. **Recall under test** — answer recall questions about TODAY using memory inject, not training-time guesses.

## Tools each member must master
- Memory recall: read curated lessons from `data/registries/team_memory/{member}/curated/`
- Skill invocation: each member has their own tool (`qsb_wren_local_agent.py`, `qsb_hermes_local_agent.py`, `qsb_iquest_code_review.py`, `qsb_consult_external.py`)
- F47 stamping: every meaningful action → row in `data/registries/qsb_tower_activity_tail.jsonl`

## Pass bar
- 3/3 recall test ✓
- Domain skill demo ✓
- Tool use without crash ✓
- 1 dissent / find-bug task ✓
