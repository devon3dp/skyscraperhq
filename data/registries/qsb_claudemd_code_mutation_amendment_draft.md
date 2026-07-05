# CLAUDE.md amendment DRAFT — code mutation bench

**Authored by:** Wren (2026-06-13, this session)
**Triggered by:** Ross 2026-06-13 quote: "so i give full permisson to you and
wren to allow rewriting of code put this in the helix but code must be run
first in sandbox etc and must pass and be signed off before you install"

**Status:** DRAFT. Not yet applied to CLAUDE.md. Wren will NOT edit CLAUDE.md
until Ross says "save it" or pastes the amendment into the file himself.

---

## Proposed section to append to CLAUDE.md (after the 2026-06-10 section)

```
================================================================================
2026-06-13 Ross authorization — bounded code mutation via sandbox + multi-sig

The F47 workshop bench is authorized: Wren and her F47 crew (builder /
architect / graphic_designer / decorator / fitter roles) may now propose AND
apply code changes, under the following bounds.

Gate that now flips TRUE (bounded code mutation):
- maintenance_auto_repair_enabled   = true   (under the bounds below)

Gates that REMAIN LOCKED FALSE under this authorization:
- worker_execution_enabled          = false  (workers still don't act on
                                              external systems; they act ONLY
                                              on the local repo, via the bench)
- autonomous_workers_enabled        = false  (no autonomous loop dispatches
                                              real-world actions)
- provider_execution_enabled        = false
- openclaw_real_tool_execution_enabled = false
- real_money_live_trading_enabled   = false
- live_dispatch_enabled             = false
- web_access_autonomous_enabled     = false

Operational bounds (HARD, enforced by tools/qsb_proposal_sandbox.py and
tools/qsb_code_proposal_checker.py):

(1) SANDBOX FIRST. A proposal cannot accumulate sigs until it has been run
    through tools/qsb_proposal_sandbox.py and returned verdict "green".

(2) SIGNATURE THRESHOLD. A proposal applies only when it has ≥3 unique-class
    signatures from {coders_team, team_assistants, wren_crew, wren_herself,
    ross}. Wren herself counts as one class; Ross counts as one class.

(3) SAFETY-TAGGED PATHS. The bench REFUSES, regardless of sigs:
      - CLAUDE.md
      - floors/floor_28_security_department/vault/
      - tools/qsb_consult_external.py
      - tools/qsb_oanda.py and src/tower/qsb_floor41_oanda
      - any .env file
      - data/registries/qsb_proposal_autoapply_gate.json (the gate itself)

(4) AUDIT TRAIL. Every applied patch writes a row to
    data/registries/qsb_code_apply_audit.jsonl: {ts, proposal_id, target_files,
    sigs[], sandbox_verdict, applier, sha_before, sha_after}.

(5) KILL SWITCH. The gate at data/registries/qsb_proposal_autoapply_gate.json
    can be flipped enabled=false at any time. The checker will then surface
    proposals as ready-for-Ross-review only; nothing auto-applies.

(6) NON-AUTONOMOUS DISPATCH. Workers propose. The HEARTBEAT applies (when sigs
    + green verdict). No worker calls the apply endpoint directly.

Use cases authorized under this section:
- F47 makeover team (decorators / graphic designers / fitters) tuning cockpit
  CSS, JS, scene materials based on the photo evolution report
- F47 builders patching cockpit JS bugs surfaced by the audit crew
- F47 architects proposing structural moves (panel reorganization, new floor
  windows)

NOT authorized under this section (would require a new CLAUDE.md edit):
- editing CLAUDE.md itself
- editing the vault or any .env file
- flipping any execution gate
- editing the bench's own enforcement code

================================================================================
```

---

## How to apply this amendment

Three options:

**A. Ross applies it:** Ross opens CLAUDE.md, pastes the block above at the end,
   saves the file. The gate registry then flips enabled=true on the next tick.

**B. Ross verbally authorizes Wren to apply it:** Ross says "save the
   amendment" or similar. Wren writes the same block into CLAUDE.md and
   stamps a F47 record.

**C. Ross rejects or modifies:** the draft sits in this file unapplied. Wren
   continues with the bench DISABLED (sigs collected, nothing auto-applied).

Until option A or B happens, the bench MECHANISM is built but the gate is OFF.
The checker shows proposals as "ready for Ross review" instead of auto-applying.
