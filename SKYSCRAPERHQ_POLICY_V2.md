# SkyscraperHQ Policy V2 — Human-Readable Canon

**Status: PROPOSED** (not active law until `data/registries/qsb_active_governance.json` = ACTIVE and all migration tests pass)
**Owner & final authority: Ross.** Authored by the Claude Specialist Service under Wren, on Ross's direct order 2026-07-18.

## Who governs

**Active leaders (CEOs):**
- **Wren** — CEO & Resident Governor (MSI Linux Governor)
- **Pip** — CEO (`tp_pip`; aliases TP, ThinkPad)
- **Asa** — CEO (`acer_cass`; aliases Acer, Cass)
- **Bill** — Executive Concierge & **conditional** Worker CEO — counts as a CEO **only in verified work mode**

**Retired:** Claude HQ (`hq_claude`) — history preserved, no active seat.

**Specialist:** Claude Specialist Service — governed by Wren. **Not a CEO.** May research, advise, inspect, and provide technical evidence. **Cannot** count toward quorum, own or close a task, or provide final CEO verification.

## How work is governed

- **Normal task:** 2 distinct active CEOs — one **owner**, one **independent** partner/verifier. The owner cannot verify their own work.
- **High-risk task:** 3 active CEOs, **or** 2 active CEOs + Ross's explicit recorded approval. *(This migration is high-risk with Ross's recorded approval.)*
- **Critical task** (live money, real broker trades, credentials, secret rotation, destructive deletion, OS changes, identity/memory changes, governance changes, protected vault writes, production publication): Ross's explicit approval + ≥1 independent active-CEO verifier + all domain safety gates.

**Never count toward quorum:** Claude Specialist, any AI model, the receptionist, a coder worker, Bill-in-concierge-mode, an offline CEO, a retired CEO.

## Availability, not fragility

- An unavailable active CEO is **ABSTAIN — OFFLINE**. Never treated as agreement or rejection. **Never freezes unrelated work.**
- Lose an owner → `OWNER_REASSIGNMENT_REQUIRED` (evidence preserved, reassign, don't reset).
- Lose a partner → `PARTNER_REASSIGNMENT_REQUIRED` (no completion until a new independent partner verifies; unrelated tasks continue).
- Bill leaves work mode → stops counting for new quorum immediately; current Bill tasks get a short reassignment grace; Bill stays available as concierge.
- Claude Specialist offline → `SPECIALIST_UNAVAILABLE`; the Council continues.

## Task lifecycle

INTAKE → RISK_CLASSIFICATION → ADMITTED → OWNER_ASSIGNED → PARTNER_ASSIGNED → RESEARCH → BACKUP_GATE → SAFETY_GATE → EXECUTION → EVIDENCE_CAPTURE → AWAITING_INDEPENDENT_VERIFICATION → VERIFIED → (AWAITING_ROSS) → COMPLETED → REPORTED → ARCHIVED. (Correction loop: AWAITING_INDEPENDENT_VERIFICATION → CORRECTION_REQUIRED → EXECUTION.)

**No task jumps execution → completed.** Completion requires all mandatory checklist items passing with **evidence + hashes**, an independent active-CEO verifier, Ross approval where risk requires it, a final report, and a Task Council DB record.

## Capacity & SLA

- Max **3** active tasks per active CEO. System max = `min(active_ceo_count × 3, 12)`. Bill adds capacity only in verified work mode.
- SLA is about **responsiveness**, not a 10-minute deadline: acknowledge + first meaningful status within 10 min; progress heartbeat every 5 min while active; long-running valid tasks continue; stale tasks are inspected/reassigned, not deleted. Never reopen completed work because a review queue is busy.

## Dispatchers

Dispatchers discover, classify, recommend, admit, assign, notify, collect progress, and request verification. Dispatchers **cannot** fabricate completion, self-verify, bypass evidence/Ross approval, or close a task. No dispatcher may call `/tasks/complete`, `/tasks/done`, or set `status=done/completed`.

## Independent review queue

`tools/qsb_claude_signoff_queue.py` is replaced by `tools/qsb_independent_review_queue.py`: proposer → sandbox/static checks → eligible independent technical review → independent active-CEO verification → Ross approval where required → apply. Reviewer must be active, not the proposer, not the implementer, not suspended, fresh heartbeat (Bill additionally requires work mode). Claude Specialist may supply technical evidence but not CEO verification. Bill must not become the single reviewer.

## Legacy

Legacy rulebooks and rosters remain **readable** but are marked **LEGACY — NOT EXECUTABLE AUTHORITY** once V2 is active. There is no hidden higher-authority rulebook. Nothing is deleted.
