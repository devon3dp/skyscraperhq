# Wren Workflow v2 — Pipelined Batches with Certifier Gates + Reassignment

## 1. The bottleneck today
Single-thread agent dispatch; Wren reads each report serially; certification is informal; deliverables don't always land on disk; **finished agents are abandoned** instead of reassigned to the next item in the queue.

## 2. The v2 pipeline
Backlog = a JSON plan (e.g. `qsb_f47_floor_buildout_plan.json`) with per-item descriptors. Discover produces it. Builder batches consume 5 items at a time in parallel. Certifier verifies all 5. Recorder stamps F47 + diary. Rejects re-enter the builder queue with the certifier's feedback attached. **Finished builder agents are not retired — they are reassigned via `SendMessage` to the next item.**

```
[backlog]  →  [discover]  →  [5-builder batch]  →  [certifier]  →  [recorder]  →  [done]
                              ↑__________________| (re-queue on reject)
                              ↑__________________| (reassign idle agent via SendMessage)
```

## 3. Concurrency rules
- 5 builders per batch (within Anthropic's per-workflow cap of 16 concurrent)
- 1 certifier per batch
- Auger consult ($0.0002–0.0005) replaces the certifier for binary go/no-go items
- Never spawn >25 agents from a single turn without explicit user authorization
- Idle batch slots get filled from the next batch in the queue

## 4. Agent reassignment (Ross rule, 2026-06-14)
When a builder agent returns its deliverable AND the backlog has more items in the same category, **reassign via `SendMessage(to: <agentId>, prompt: "next item: <next-item-descriptor>")`**. Don't spawn a fresh agent for a same-category item. Why: each reassignment preserves the agent's accumulated context (style, code-pattern familiarity, sandbox awareness) and skips the cold-start cost. Reassignment ALSO applies to certifiers — one certifier can verify 3–5 batches before needing relief.

When NOT to reassign:
- The next item is from a different category (e.g. ml_data agent shouldn't decorate)
- The agent failed certification on its last item — fresh start is cleaner than carrying bad assumptions
- The agent's last report showed context fatigue (long, vague, scope-creeping)

## 5. Verdict types
- ✅ certified — item flips to `completed`
- 🟡 caveat — item flips to `completed` AND a new follow-up task opens
- 🔴 reject — item re-enters builder queue with the certifier's verdict text as feedback

## 6. Stamping discipline
(per memory `feedback_stamp_every_job_boundary`)
- F47 record at `job_started` for each batch
- F47 record at `job_completed` or `job_blocked` for each item
- Diary line at batch start + batch end
- Memory file ONLY for non-obvious facts (not for every shipment)

## 6.5 Learning loop (Ross rule, 2026-06-14)
**Every agent's final report MUST include a `lessons_learned` block** — a structured paragraph naming: what was unexpected, what changed during the work, what the agent would do differently next time, what assumption proved wrong. The recorder appends each lesson to `data/registries/qsb_f47_agent_lessons.jsonl` with `{ts, agent_id, batch_id, item_id, lesson_text, category}`. Future builder briefs include a `lessons_priors` section that grep-fetches relevant lessons from the jsonl. Recurring lessons (≥3 occurrences in 7 days) get promoted to a real memory file. Without this loop, every agent re-learns the same gotchas — wasted budget, wasted Wren context.

## 7. Pipeline failure modes + recovery

| Failure | Recovery |
|---|---|
| certifier times out | fall back to Auger consult |
| builder returns no deliverable | re-dispatch with stricter brief + cite the original |
| reassigned agent gives stale answer | retire the agent, spawn fresh |
| Wren context fills | stop spawning, drain queue, summarize, then resume |
| Auger budget exhausted | escalate to Helm/Ross |

## 8. When to use 25 agents vs 5
- 5 is the default
- 25 only for explicit scope expansion (Ross says "Open Day", "F47 build-out", "the works")
- 25 = 5 batches × 5 builders, with reassignment carrying agents from batch N to batch N+1 where category matches

## 9. Migration plan
Adopt v2 immediately. The current F47 floor build-out is the first v2 run. Open Day sprint items (#10–#22) retroactively follow the same pattern.

## 10. Lineage
- `feedback_certify_every_agent_shipment` — every agent's work must be certified
- `feedback_signoff_required` — verify the user-facing path
- `feedback_team_on_every_job` — dispatch team + F47 record per job
- `feedback_helm_handoffs_are_bounded` — scope stays bounded under helm windows

— Wren / F47 / 2026-06-14
