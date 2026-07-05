"""Strategic next-steps recommendations.

The author of this module (Claude) inspected the live system and wrote
this as an architectural recommendation rather than a static checklist.
It reads `audit_latest.json` and chooses priorities based on real gaps.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def _now(): return datetime.now(timezone.utc).isoformat()


def _latest():
    p = ROOT / "state/tower_ops/audit_latest.json"
    if not p.exists():
        from .tower_audit import run_full
        return run_full()
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def report():
    L = _latest()
    critical = L.get("critical_failures") or []
    failures = L.get("failures") or []
    warnings = L.get("warnings") or []
    cats = L.get("category_scores") or {}

    working_well = [
        "21-route Tower Operations V2/V3 backend is fully wired and stamping the safety contract on every payload.",
        "All 23 execution locks remain false; `lock_count_true: 0` across `/api/unified` and every sub-block.",
        "155+ named workers carry deterministic badges (`QSB-WORKER-<floor3>-<dept>-<NNN>`) and access cards.",
        "Read-only OANDA/Binance/Stocks telemetry behaves honestly — LIVE_READ_ONLY only when credentials exist, otherwise NOT_CONFIGURED with an explicit reason.",
        "Kernel chat now replies live: the recursion in `kernel_dialogue_adapter.load_kernel()` is caught and the chain degrades gracefully into the local Ollama model.",
        "Recruitment Agency, Maintenance, Security, IT, Research, Accounts (Floor 44), Quantum (Floor 45), Lifts (Floor 22), Model Operations (Floor 24), and Training Academy (Floor 8) each have a real backend module + endpoint + UI console.",
    ]
    half_built = [
        "Lift animations are visualised as a rolling occupancy snapshot, but workers do not yet *board/exit* in the SVG renderer.",
        "Trading telemetry is honest about NOT_CONFIGURED but Binance open-orders and Stocks positions/PnL gateway helpers are still missing — once added, the telemetry flips to LIVE_READ_ONLY automatically.",
        "Penthouse kernel chat replies via the local Ollama lane through the symbolic+local-model fallback; the *underlying* kernel core constructor recursion is still present and a proper fix in `kernel_core` would let the kernel give richer status/analysis blocks.",
        "Worker certifications are seeded from team→role mapping, but per-worker enrolment/exam flow needs a UI page next to the Worker ID Card.",
        "Audit can run but recommendations are advisory — no enforcement (which is correct for V3) and no auto-remediation (which the brief explicitly forbids).",
    ]
    missing = [
        "QA/Testing and Facilities departments are not yet assigned to vacant floors.",
        "No floor accountant card *visualisation* inside each floor's interior (data is present in `/api/accounts/floor_accountants`).",
        "Manager-office and overseer-balcony 3D markers inside floor interiors are listed in the renderer options but not yet drawn as SVG glyphs.",
    ]
    unsafe_to_unlock = [
        "OpenClaw execution stays false until: (a) all OpenClaw-readiness workers are fully certified, (b) Security floor signs off on a separate explicit unlock command, (c) Compliance floor publishes the unlock-policy disclaimer.",
        "Live trading stays false until: (a) Trading Telemetry Auditor (Floor 43) certifies every label, (b) Floor Accountant for that venue signs off, (c) Risk Compliance Officer (Floor 32) issues an explicit unlock command.",
        "AirLLM cannot be wired into AutoLoop. The advisory lane stays manual-invocation-only.",
        "External providers stay locked.",
        "Autonomous web access stays locked.",
        "Maintenance auto-repair stays locked.",
    ]

    next_phases = [
        {
            "priority": 1,
            "title": "Fix the underlying kernel_core recursion (not just catch it)",
            "reason": "Right now `kernel_dialogue_adapter.load_kernel()` catches `RecursionError` and degrades to the symbolic + local-model path. That works (you can chat the kernel), but the kernel's own `status()` and `analyze()` blocks never run — so the kernel chat's structural answers (about workers/locks/floors) come from the local model's general knowledge rather than from kernel introspection. Fixing the recursion in `kernel.kernel_core` would let the bridge return the rich kernel context the dashboard was originally designed for.",
            "files_likely_involved": [
                "rebased_kernel/kernel/kernel_core.py (in REB_BASE)",
                "src/tower/dormant_kernel_adapter.py",
                "src/tower/kernel_dialogue_adapter.py",
            ],
            "risk": "Touching the kernel core can trip the activation gate. Mitigation: a read-only repro script in a separate venv first; then propose a minimal patch; never bypass the activation safety check.",
            "acceptance_test": "POST /api/kernel_chat with 'list floor 30 locks' returns kernel-introspected lock map, not Ollama paraphrase.",
        },
        {
            "priority": 2,
            "title": "Add Binance open-orders + Stocks positions/PnL gateway helpers",
            "reason": "Trading telemetry is the one place where adding two small helpers in existing gateways unlocks five 'NOT_CONFIGURED' endpoints into LIVE_READ_ONLY. No new credentials needed; the helpers just call existing read-only Binance + Alpaca paths.",
            "files_likely_involved": [
                "src/tower/binance_floor.py (add open_orders + my_trades read-only)",
                "src/tower/stock_exchange_floor.py (add positions + portfolio history)",
                "src/tower_ops/trading_telemetry.py (flip not_configured → live)",
            ],
            "risk": "Low — read-only paths only. The execution gates in BinanceGateway already refuse signed POST. Mitigation: per-call test that the path is in the read-only allowlist before calling.",
            "acceptance_test": "/api/trading/binance/orders and /api/trading/stocks/positions return LIVE_READ_ONLY when creds are set.",
        },
        {
            "priority": 3,
            "title": "Render manager-office, overseer-balcony, accountant-card glyphs inside floor interiors",
            "reason": "The /api/floor_detail block already carries floor_manager, zone_manager, overseers, roster. The user can see this in the right-rail data block but the *interior visual* still uses the V2 desk layout. Adding three small SVG glyphs per floor gives Ross immediate at-a-glance visibility of who's running each floor.",
            "files_likely_involved": [
                "src/dashboard/static/qsb_floor_interior.js",
                "src/dashboard/static/cockpit.css",
            ],
            "risk": "Purely visual. No backend changes.",
            "acceptance_test": "Open Floor 41 — see Manager Office glyph + Overseer Balcony glyph + Accountant Card glyph inside the floor interior, not only in the right rail.",
        },
        {
            "priority": 4,
            "title": "Build the QA/Testing and Facilities departments on floors 46/47 or 39/40",
            "reason": "Audit reports them as 'missing/unassigned'. They are the last two departments in the audit's coverage check. Assigning them to existing department floors (e.g. Floor 9 Quality Assurance → QA/Testing; Floor 40 Prototype Systems → Facilities) closes the inventory.",
            "files_likely_involved": [
                "src/tower_ops/extra_workers.py (add QA + Facilities staff)",
                "src/tower_ops/missing.py (mark covered)",
            ],
            "risk": "Zero. Pure metadata + UI.",
            "acceptance_test": "/api/tower_ops/missing reports `missing_count: 0`.",
        },
        {
            "priority": 5,
            "title": "Per-worker enrolment + exam UI tied to badge access",
            "reason": "The Certification Engine fully exists in V3 (`POST /api/training/enrol`, `complete_lesson`, `certify_worker`, `revoke_certification`). What's missing is the *worker-level enrolment page* inside the Worker ID Card. Adding it would let any user (with the right manager access level) certify a worker in two clicks — closing the manager → training → certification loop visually.",
            "files_likely_involved": [
                "src/dashboard/static/cockpit.js (Worker ID Card extension)",
                "src/dashboard/static/cockpit.css",
            ],
            "risk": "Low — endpoints already exist with safety-stamped responses.",
            "acceptance_test": "Open any Worker ID Card → click 'Enrol in Safety Locks 101' → reload card → `completed_courses` includes `safety_locks_101`.",
        },
    ]

    highest_priority = "Priority 1 — fix the kernel_core recursion so the kernel returns real introspection blocks rather than relying on the symbolic+local-model fallback."
    highest_priority_floor = "Floor 8 (QSB Training Academy) — already named and staffed, but the school UI deserves its category-specific console next phase so manager/overseer/accountant glyphs are visible inside the academy interior."
    highest_priority_worker = "A *Kernel Recursion Researcher* on Floor 3 (Research Department) — to specifically own the priority-1 bug fix above."
    highest_priority_graphics = "Lift cars that *visibly transport workers* between floors in the SVG renderer. The backend already tracks lift occupancy by badge; the renderer just needs to draw the workers inside the moving lift glyph rather than orbit their home floor only."

    blocking_bug = ("`kernel.kernel_core.QSBKernelCore.__init__` recursion. Once that is fixed, the chat returns rich kernel introspection, "
                    "the Penthouse animations get real telemetry, and the manager-report pipeline reaches Kernel with structured payloads instead of Ollama summaries.")

    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_OPERATIONS_V3",
        "what_is_working_well": working_well,
        "what_is_half_built":   half_built,
        "what_is_missing":      missing,
        "what_is_unsafe_to_unlock": unsafe_to_unlock,
        "must_fix_before_openclaw_operational": [
            "Certify every OpenClaw-readiness worker via /api/training/certify_worker.",
            "Compliance Floor 32 must publish the unlock-policy disclaimer.",
            "Security Floor 28 must explicitly sign off via a NEW per-floor unlock command (not implemented in V3 — by design).",
        ],
        "must_fix_before_live_trading_considered": [
            "Trading Telemetry Auditor (Floor 43) certifies LIVE_READ_ONLY labels.",
            "Floor Accountant on Floor 44 produces a verified trading_summary covering at least 24h.",
            "Risk Compliance Officer (Floor 32) issues an explicit unlock command.",
            "Order Door Locked badge on every trading floor flips to a separately gated 'paper-orders-OK' badge.",
        ],
        "must_fix_before_airllm_manual_query_from_cockpit": [
            "Confirm POST /api/models/manual_airllm_advisory returns descriptor (already works).",
            "Add a Big Model Prompt Clerk-facing form in Floor 23 console with an explicit consent dialog.",
            "Never wire this into AutoLoop.",
        ],
        "next_5_build_phases": next_phases,
        "highest_priority_recommendation": highest_priority,
        "highest_priority_floor":  highest_priority_floor,
        "highest_priority_worker": highest_priority_worker,
        "highest_priority_graphics": highest_priority_graphics,
        "single_bug_blocking_most_functionality": blocking_bug,
        "highest_priority_system_choice": (
            "Kernel chat. Reason: it's the *single* surface where the user converses with the tower; everything else flows from there. "
            "Lifts/accounts/training/telemetry already work via their own endpoints and consoles; fixing the underlying kernel recursion "
            "would simultaneously upgrade chat, the Penthouse, the Concierge/Butler, and the manager-report pipeline."
        ),
        "category_scores_observed": cats,
        "evidence_pointer": "GET /api/audit/latest for the full 15-category result set.",
    })
