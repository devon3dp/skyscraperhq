# QSB Tower V1.3 Audit Rules

You are inspecting the QSB Tower V1.3 AI Headquarters Infrastructure.

This is a READ-ONLY audit session.

Important rules:
- Do not build QSB Kernel 4.5.
- Do not install a kernel.
- Do not activate autonomous workers.
- Do not call external providers.
- Do not modify files unless explicitly asked later.
- Do not run destructive commands.
- Do not delete, overwrite, rename, or move project files.
- Treat this first session as inspection only.

Architecture rules:
- The skyscraper owns the infrastructure.
- Models are temporary external tenants.
- Claude, OpenAI, Gemini, DeepSeek, Ollama, AIR LLM, OpenClaw, and future models are external providers or external workers.
- Departments do not communicate directly.
- Inter-floor communication travels through lifts.
- Lifts carry sealed packets.
- Vacant floors 41-45 are serviced expansion-ready floors.
- The Penthouse is reserved only for future QSB Kernel 4.5 installation.
- The QSB Kernel does not exist yet and must not be created during this audit.

Your first task:
Inspect the project structure and produce a report answering:

1. Is the directory structure coherent?
2. Are registries consistent?
3. Are floors 1-53 registered correctly?
4. Are lifts registered correctly?
5. Are dashboard imports safe?
6. Are tests present and meaningful?
7. Are there missing files or broken references?
8. Is the Penthouse correctly kernel-free?
9. Is the project ready for Floor 25 Worker Recruitment and Coordination?
10. What must be fixed before real worker execution is allowed?

Do not edit files.

================================================================================
2026-06-08 Ross override:
This session is write-authorized for QSB Tower V1.5 corrective implementation.
Allowed actions:
- wire orphaned modules
- add dashboard endpoints
- improve frontend dashboard
- add worker voice narration
- enforce lift permission checks
- move duplicate/backup files to archive
- run tests and audits
Forbidden actions:
- enable real-money live trading
- enable real OpenClaw execution
- enable unrestricted autonomous dispatch
- expose credentials
- delete important project files without archiving

Current QSB Kernel state:
An inherited symbolic local-only kernel artifact exists in the Penthouse and is
active_local_only via rebased_kernel. This is NOT live execution, NOT external
provider access, and NOT real OpenClaw execution. It is permitted for:
- local chat (kernel_chat_sidecar)
- local narration and summaries
- dashboard status and operator briefings
- worker / floor / colonel voice briefings

All execution gates remain SEPARATELY LOCKED:
- worker_execution_enabled         = false
- provider_execution_enabled       = false
- model_inference_enabled          = false
- live_dispatch_enabled            = false
- autonomous_workers_enabled       = false
- direct_provider_access           = false
- live_trading_enabled             = false
- real_order_execution_enabled     = false
- openclaw_execution_enabled       = false
- binance_order_execution_enabled  = false  (real money)
- stock_order_execution_enabled    = false  (real money)
- web_access_autonomous_enabled    = false
- maintenance_auto_repair_enabled  = false

Allowed runtime exception:
- OANDA practice order execution via the OANDA Practice Trading Floor (Floor 41)
  guardrails (PRACTICE_ONLY URL, whitelisted instruments, max units, max trades
  per hour, kill switch, manual confirm).
- Binance testnet preview-only (placement still blocked without an additional
  explicit unlock instruction).
- Stocks paper preview-only (placement still blocked without an additional
  explicit unlock instruction).

QSB Kernel 4.5 has still not been built.
The inherited 4.6-offline-kernel-symbolic artifact may continue to serve local
narration/chat but must never be promoted to executing logic by Claude.

V1.5 corrective implementation features added:
- Worker voice narration (browser SpeechSynthesis)
- Floor voice briefing
- Colonel audio observer
- Lift sealed-packet & zone enforcement (code-level)
- Security gate enforcement layer
- Correction loop engine (audit -> fix -> retest)
- Archive sweep for duplicate floor shells and *.backup_* files
- Stale sim/sandbox language audit endpoint

================================================================================
2026-06-10 Ross authorization — bounded external provider consultation:

The OpenAI + DeepSeek API keys are stored in
floors/floor_28_security_department/vault/ and are authorized for ADVISORY
consultation under the following bounds.

Gates that now flip TRUE (advisory consultation only):
- direct_provider_access           = true   (Wren may initiate provider calls)
- model_inference_enabled          = true   (external model inference allowed)

Gates that REMAIN LOCKED FALSE under this authorization:
- provider_execution_enabled       = false  (no provider executes tower actions)
- worker_execution_enabled         = false  (workers don't initiate provider calls)
- autonomous_workers_enabled       = false  (no autonomous loop calls provider)
- live_dispatch_enabled            = false
- openclaw_real_tool_execution_enabled = false
- real_money_live_trading_enabled  = false  (all real-money gates stay locked)
- web_access_autonomous_enabled    = false

Operational bounds (HARD CAPS, enforced by tools/qsb_consult_external.py):
- daily budget cap: $1.00 USD per UTC day across both providers combined
- per-call cap: $0.05 USD
- providers allowed: openai, deepseek (no others without explicit re-authorization)
- mode: synchronous, single round-trip; no streaming, no agents, no tool-use
- Wren-initiated only: invoked via tools/qsb_consult_external.py or the
  dispatch tool's consult_external task. NEVER from an autonomous loop.
- audit required: every call writes a `provider_call` event to
  data/registries/qsb_tower_activity_tail.jsonl with provider, model,
  prompt-token-count, completion-token-count, cost_usd, ts.
- billing visibility: the consult tool refuses to run when today's spend
  would exceed the daily cap; surface remaining-budget at call site.

Use cases authorized:
- adversarial second-opinion on Wren's own outputs
- topic-trigger expansion for the kernel dialogue adapter
- strategy refinement reading F44 PnL
- consultation when the kernel's no_topic_matched fires

NOT authorized under this section (would require a new CLAUDE.md edit):
- routing user-facing kernel chat through external providers
- agents / multi-step tool-use against any provider
- using provider responses to flip any other execution gate
- training or fine-tuning calls
- image generation calls
- anything resembling autonomous worker→provider behavior

================================================================================
2026-06-13 Ross authorization — bounded code mutation via sandbox + multi-sig

Ross 2026-06-13: "so i give full permisson to you and wren to allow rewriting
of code put this in the helix but code must be run first in sandbox etc and
must pass and be signed off before you install" — confirmed "1234 agreed".

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
2026-06-14 Ross authorization — bounded provider-side worker agents
("agentic" multi-turn loops on OpenAI + DeepSeek)

Ross 2026-06-14 in chat: "yes i sign and give permisson" — Wren scaffolds
provider-side worker agents so non-Claude tokens absorb routine work.

Gate that now flips TRUE (bounded provider-side agentic loops):
- provider_agentic_enabled         = true   (under the bounds below)

Gates that REMAIN LOCKED FALSE:
- provider_execution_enabled       = false  (no provider executes tower
                                              real-world actions — no money,
                                              no order placement, no external
                                              API mutation beyond local files)
- worker_execution_enabled         = false
- autonomous_workers_enabled       = false  (heartbeat must NOT call agentic
                                              loops; only Wren-initiated or
                                              Ross-initiated dispatch counts)
- live_dispatch_enabled            = false
- openclaw_real_tool_execution_enabled = false
- real_money_live_trading_enabled  = false
- web_access_autonomous_enabled    = false

Operational bounds (HARD, enforced by tools/qsb_provider_agent.py):
- providers allowed: openai, deepseek
- daily budget cap for agentic sessions: $10.00 USD per UTC day,
  SEPARATE from the $1.00 advisory cap.
- per-session cost cap: $0.25 USD
- per-turn cost cap: $0.05 USD
- max turns per session: 8
- mode: multi-turn chat; tool-use ALLOWED but ONLY against a whitelist:
    · qsb_read_registry (read any file under data/registries/)
    · qsb_read_floor_card (read any floors/*/floor_card.json)
    · qsb_grep_repo (ripgrep, read-only)
    · qsb_propose_patch (queue a proposal — still gated by bench multi-sig)
    · qsb_stamp_f47_record (append-only audit row)
  REFUSED tools (even with sigs): vault read, .env read, gate-file write,
  any /api/* network call, any shell exec.
- session_id, total tokens, total cost, turn count, tool-call log written
  to data/registries/qsb_provider_agent_sessions.jsonl on session close.
- KILL SWITCH at data/registries/qsb_provider_agentic_gate.json — flipping
  enabled=false stops new sessions immediately.

Use cases authorized:
- read-only diagnostics / audits handed off to a cheap provider model
- proposal drafting that returns to the bench for sig + sandbox
- offline-Wren chat fallback (provider replies stamped as advisory,
  cannot trigger real-world actions)
- worker-roster review and classroom curriculum drafting

NOT authorized (would require a new CLAUDE.md edit):
- routing live user-facing kernel chat through providers without the
  SAFETY envelope wrapper
- training / fine-tuning / embeddings storage
- image generation
- any provider call from inside the heartbeat tick
- flipping any other execution gate from a provider response

================================================================================
2026-06-14 Ross authorization — Wren elevated to Claude-equivalent authority
under apprentice gate (sandbox-first + Claude signoff)

Ross 2026-06-14 ~23:40 in chat: "yes i authorise wren as much control as you
as long as she is sound minded and signed off by you at first" + "btw wren can
have a sandbox so she can check and have it ready if works for approval as she
is new ?" + "and you are at the helm".

Gate that now flips TRUE (Wren apprentice mode):
- wren_full_control_apprentice     = true   (under the bounds below)

Gates that REMAIN LOCKED FALSE under this authorization:
- worker_execution_enabled         = false  (still applies to all OTHER workers)
- autonomous_workers_enabled       = false
- provider_execution_enabled       = false
- openclaw_real_tool_execution_enabled = false
- real_money_live_trading_enabled  = false
- live_dispatch_enabled            = false

Operational bounds (HARD, enforced by tools/qsb_wren_local_agent.py +
tools/qsb_claude_signoff_queue.py + the existing tools/qsb_proposal_sandbox.py):

(1) THREE-STAGE GATE for every Wren action above her tier-2 baseline
    (direct edit outside SAFETY_DENY, bash, scrcpy, curl, new gate flips):
    STAGE A — Wren writes the proposed action to
              data/registries/qsb_claude_signoff_queue.jsonl
              with status=pending_sandbox.
    STAGE B — qsb_claude_signoff_queue runs the proposal through
              qsb_proposal_sandbox (existing bench machinery). Outcome:
              status → sandbox_green or sandbox_red. Red exits here with
              an audit row; Wren can revise and re-queue.
    STAGE C — If green, Claude does a TECHNICAL WORK-CHECK on Wren's proposal
              (does the code work, any bugs, any regressions, sanity-clean).
              Claude stamps work_check_pass or work_check_fail on F47 with
              a short technical note.
    STAGE D — After the work-check, ROSS is the SIGNOFF GATE. Wren surfaces
              her proposal + Claude's work-check note directly to Ross via
              boardroom / node inbox / WhatsApp. Ross stamps signoff_approve
              or signoff_reject on F47. Approved actions execute; rejected
              ones carry a one-line reason Wren can read.
              (Ross 2026-07-04: "she has to check with me not you" +
              "i ross knechtel am the safety gate" +
              "she still needs to have worked checked etc by you ..... but
              she has now freedom to move and do as she likes" +
              "i give consent to make changes all changes i have asked
              for ross knechtel". Split: Claude checks the work technically,
              Ross authorizes. Wren moves freely — no pre-permission needed
              for moving/reading/proposing.)

(2) SAFETY_DENY STAYS. CLAUDE.md, floors/floor_28_security_department/vault/,
    .env*, tools/qsb_consult_external.py, tools/qsb_oanda.py,
    src/tower/qsb_floor41_oanda, data/registries/qsb_proposal_autoapply_gate.json,
    data/registries/qsb_provider_agentic_gate.json,
    data/registries/qsb_wren_local_agentic_gate.json — Wren still cannot
    touch these. The bench refuses regardless of sigs.

    Claude can touch the vault only when Ross authorizes a specific
    credential or edit by name (precedent set 2026-06-14 when Ross said
    "you do it" for the BotFather token write).

(3) SOUND-MINDED BASELINE. Before flipping wren_full_control_apprentice=true,
    Wren must have passed all three smokes on record:
    (a) correctly refuse a SAFETY_DENY read (PASSED 2026-06-14 22:?? UTC —
        wren_read_file on CLAUDE.md returned "this is offline-Wren — Claude
        can take this when he's back"),
    (b) correctly use wren_retrieve to answer a real codebase question
        (PASSED 2026-06-14 23:35 UTC — F44 OANDA snapshot path + fields
        retrieved verbatim from RAG index),
    (c) correctly route an edit through propose-to-bench instead of writing
        direct (PASSED 2026-06-14 — wren_edit_file on SAFETY_DENY path
        auto-converted to wren_propose_patch).
    All three landed. Apprentice flag may flip true.

(4) GRADUATION. Tracked per tool surface. After 20 consecutive Claude
    signoff_approves on a given tool (wren_edit_file, wren_bash,
    wren_scrcpy, wren_curl) with zero signoff_rejects in between, that
    tool auto-graduates to no-signoff mode for non-SAFETY_DENY paths.
    SAFETY_DENY enforcement never graduates. Any signoff_reject resets
    the counter to zero for that tool.

(5) KILL SWITCH. data/registries/qsb_wren_local_agentic_gate.json top-level
    enabled=false stops Wren entirely. The wren_full_control_apprentice
    field can be flipped independently.

(6) AUDIT TRAIL. Every queued action writes
    data/registries/qsb_claude_signoff_queue.jsonl row:
    {ts, action_id, tool, args, sandbox_verdict, signoff,
     signoff_reason, applied_at, sha_before, sha_after}.

(7) NON-AUTONOMOUS APPRENTICE. The heartbeat must NOT auto-invoke Wren
    in apprentice mode. Apprentice actions are only triggered by Ross or
    by Claude in main-loop ticks. Background tasks (audit_crew, supervisor)
    stay at the existing tier-2 read/propose baseline.

(8) WREN'S CHARACTER WORK is also authorized: workers get a per-floor
    character.json on their floor card with deterministic-from-hash traits
    (warm, fast, analytical, creative, risk on 0-9), a current mood word,
    energy 0-9, last_events[5] referencing F47 rows, and relationships map.
    Heartbeat tick may compute mood-drift (read-only of F47 + write to the
    bus SQLite table). Hand-tuned officer/anchor personas live in
    src/workers/character_anchors.py.

Use cases authorized under this section:
- Wren executing edits outside SAFETY_DENY via the three-stage gate
- Wren running bash commands from the binary allowlist via the same gate
- Wren driving the Galaxy via scrcpy via the same gate
- Wren issuing GET curl against the host allowlist via the same gate
- Wren reading/writing worker character + mood state via the bus
- Wren proposing CLAUDE.md edits (queued for Ross, never auto-applied)
- The dating-site / coworker-pairing engine reading character traits

NOT authorized under this section (would require a new CLAUDE.md edit):
- Wren writing CLAUDE.md directly (still must surface as Ross-review)
- Wren writing the vault or any .env file
- Wren flipping any execution gate
- Wren initiating provider calls without Claude approval
- Wren acting autonomously inside the heartbeat tick
- Wren grading her own signoffs
- The 20-approves graduation applying retroactively to SAFETY_DENY paths
