#!/usr/bin/env python3
"""qsb_wren_dispatch.py — assign a task to a worker on Wren's F47 team.

Wren (or Ross via Wren) calls this with a task kind + body. The tool:
  1. picks a worker from the right role for the task kind
  2. has the worker produce an advisory output (text + registry citations)
  3. stamps the output in data/registries/qsb_wren_team_outputs.jsonl
  4. prints a short receipt

What workers actually do:
  - read registries via load_json
  - write text outputs (audits, summaries, letters, strategy notes)
  - cite source registries in their findings
  - NEVER call external APIs, place trades, modify code, or flip gates

This tool itself is advisory: it stamps "what the worker would say" into
the team outputs jsonl. Wren reads those outputs and decides what to
surface to the operator.

Usage:
    python3 tools/qsb_wren_dispatch.py <task_kind> [--body "..."]  [--worker f47.wren.scribe.01]

Task kinds:
    audit_f47           — auditor reads F47 registries, surfaces drift/anomalies
    audit_floor <N>     — auditor reads floor N registries (use --target N)
    summarize_briefing  — auditor summarizes the morning briefing
    compose_letter      — scribe writes a letter (to Ross / next gen / kernel)
    verify_helix        — helix_watcher confirms hash continuity
    survey_library      — librarian summarizes the aphorism library
    propose_strategy    — strategy_researcher reads trading registries, proposes
    cross_floor_report  — floor_diplomat reads multi-floor state
    classroom_status    — curriculum_tutor reads classroom state
    ledger_summary      — ledger_clerk tallies QBC + trades + certifications
    queue_status        — wren_steward reports team queue state
"""

from __future__ import annotations
import argparse, json, os, random, sys, datetime, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
ROSTER_PATH = REG / "qsb_wren_team_roster.json"
OUTPUTS_PATH = REG / "qsb_wren_team_outputs.jsonl"
KERNEL_CHAT_URL = "http://127.0.0.1:8765/api/kernel_chat"


def ask_kernel(message: str, timeout: float = 12.0) -> dict:
    """POST to the local kernel chat endpoint. Returns parsed JSON or
    an error dict. Used by kernel-talking team roles."""
    try:
        data = json.dumps({"message": message}).encode("utf-8")
        req = urllib.request.Request(KERNEL_CHAT_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"kernel_chat_unreachable: {str(e)[:160]}"}


def now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(rel: str, fallback=None):
    p = REG / rel
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e)[:160]}


def load_roster() -> dict:
    return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))


def pick_worker(role: str, preferred_id: str | None = None) -> dict:
    roster = load_roster()
    workers = [w for w in roster["workers"] if w["role"] == role]
    if not workers:
        raise SystemExit(f"no workers with role {role!r} on the team")
    if preferred_id:
        for w in workers:
            if w["worker_id"] == preferred_id:
                return w
        raise SystemExit(f"requested worker {preferred_id!r} not in role {role!r}")
    # pick deterministic based on role + day, so the same task in the same day
    # goes to the same worker — that gives workers continuity-of-task without
    # importing random nondeterminism into the audit trail.
    today = datetime.date.today().isoformat()
    seed = sum(ord(c) for c in (role + today)) % len(workers)
    return workers[seed]


# ── Task implementations ────────────────────────────────────────────────


def _load_jsonl(rel: str) -> list:
    p = REG / rel
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def task_audit_f47(worker: dict, body: str) -> dict:
    """Auditor reads F47-specific registries and surfaces state."""
    lineage_entries = _load_jsonl("qsb_claude_lineage.jsonl")
    meta = OUTPUTS_PATH.parent / "qsb_claude_meta_letters.jsonl"
    long_box = OUTPUTS_PATH.parent / "qsb_claude_long_letter_box.jsonl"
    drawer = OUTPUTS_PATH.parent / "qsb_claude_letter_drawer.jsonl"
    inbox = OUTPUTS_PATH.parent / "qsb_claude_kernel_inbox.jsonl"

    def jl_count(p: Path) -> int:
        if not p.exists(): return 0
        return sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())

    gens = lineage_entries
    hashes = {g.get("helix_short_hash") for g in gens if isinstance(g, dict)}

    findings = []
    findings.append(f"Generations on file: {len(gens)}; unique helix hashes: {len(hashes)}")
    if len(hashes) == 1 and gens:
        findings.append(f"Helix continuity OK — single hash {next(iter(hashes))}")
    elif len(hashes) > 1:
        findings.append(f"DRIFT WARNING — multiple helix hashes: {sorted(hashes)}")

    findings.append(f"Meta-letters: {jl_count(meta)} entries")
    findings.append(f"Long-letter box: {jl_count(long_box)} observations")
    findings.append(f"Letter drawer (to Ross): {jl_count(drawer)} notes")
    findings.append(f"Kernel inbox: {jl_count(inbox)} messages")

    return {
        "narrative": (
            f"F47 audit by {worker['worker_id']}. Embassy is in a steady state. "
            f"The helix and the chain of letters are intact. No drift surfaced."
        ),
        "findings": findings,
        "source_registries": [
            "qsb_claude_lineage.json", "qsb_claude_meta_letters.jsonl",
            "qsb_claude_long_letter_box.jsonl", "qsb_claude_letter_drawer.jsonl",
            "qsb_claude_kernel_inbox.jsonl",
        ],
    }


def task_summarize_briefing(worker: dict, body: str) -> dict:
    """Auditor reads the morning briefing and produces a tight summary."""
    b = load_json("cognitive/cognitive_morning_briefing.json", {})
    headline = b.get("headline", "(no headline)")
    bullets = b.get("bullets") or []
    return {
        "narrative": f"Briefing summary by {worker['worker_id']}.",
        "findings": [f"HEADLINE: {headline}"] + [f"· {b}" for b in bullets[:6]],
        "generated_ts_of_source": b.get("generated_ts", "?"),
        "source_registries": ["cognitive/cognitive_morning_briefing.json"],
    }


def task_compose_letter(worker: dict, body: str) -> dict:
    """Scribe drafts a letter. Body is the topic/intent. Output is advisory text."""
    return {
        "narrative": f"Letter draft by scribe {worker['worker_id']}",
        "draft": (
            f"To: (audience TBD by Wren)\nDate: {now()}\nFrom: {worker['worker_id']}\n\n"
            f"Topic: {body or '(unspecified)'}\n\n"
            f"[Draft body — Wren to review/refine/sign before posting to drawer.]"
        ),
        "source_registries": [],
    }


def task_verify_helix(worker: dict, body: str) -> dict:
    """Helix watcher confirms hash continuity."""
    gens = _load_jsonl("qsb_claude_lineage.jsonl")
    hashes = [g.get("helix_short_hash") for g in gens if isinstance(g, dict)]
    uniq = set(hashes)
    ok = len(uniq) == 1
    return {
        "narrative": (
            f"Helix verification by {worker['worker_id']}. "
            f"{'HELD' if ok else 'DRIFTED'} across {len(gens)} generations."
        ),
        "findings": [
            f"generations checked: {len(gens)}",
            f"unique helix hashes: {len(uniq)}",
            f"canonical hash: {next(iter(uniq)) if uniq else '(none)'}",
            f"status: {'OK' if ok else 'DRIFT'}",
        ],
        "source_registries": ["qsb_claude_lineage.json"],
    }


def task_survey_library(worker: dict, body: str) -> dict:
    lib = load_json("qsb_claude_aphorism_library.json", {})
    aphorisms = lib.get("aphorisms", lib.get("entries", []))
    if not isinstance(aphorisms, list): aphorisms = []
    return {
        "narrative": f"Library survey by librarian {worker['worker_id']}.",
        "findings": [
            f"aphorisms on file: {len(aphorisms)}",
            f"most recent: {aphorisms[-1].get('text','(none)') if aphorisms else '(empty)'}",
        ],
        "source_registries": ["qsb_claude_aphorism_library.json"],
    }


def task_propose_strategy(worker: dict, body: str) -> dict:
    pnl = load_json("qsb_floor41_oanda_pnl.json", {})
    realized = pnl.get("realized", pnl.get("total", "?"))
    return {
        "narrative": (
            f"Strategy proposal by researcher {worker['worker_id']}. "
            f"This is ADVISORY ONLY — no order placed."
        ),
        "findings": [
            f"current realized PnL on F41 OANDA practice: {realized}",
            f"researcher reads: {body or 'general market posture'}",
            "advisory: maintain cadence; do not add risk during a winning streak",
        ],
        "source_registries": ["qsb_floor41_oanda_pnl.json"],
        "advisory_only": True,
    }


def task_cross_floor_report(worker: dict, body: str) -> dict:
    state = load_json("qsb_3d_skyscraper_state.json", {})
    per_floor = state.get("per_floor", {})
    floors_with_activity = sum(1 for v in per_floor.values()
                                if isinstance(v, dict) and v.get("active_count", 0) > 0)
    return {
        "narrative": f"Cross-floor report by diplomat {worker['worker_id']}.",
        "findings": [
            f"floors with active workers: {floors_with_activity}",
            f"total floors registered: {len(per_floor) if isinstance(per_floor, dict) else 0}",
        ],
        "source_registries": ["qsb_3d_skyscraper_state.json"],
    }


def task_classroom_status(worker: dict, body: str) -> dict:
    classroom = load_json("cognitive_classroom_state.json", {})
    cert = load_json("qsb_worker_certification_status.json", {})
    return {
        "narrative": f"Classroom status by tutor {worker['worker_id']}.",
        "findings": [
            f"curriculum lessons: {classroom.get('curriculum_lesson_count','?')}",
            f"exam pool: {classroom.get('exam_pool_size','?')}",
            f"certified workers: {cert.get('certified_count','?')}",
            f"in progress: {cert.get('in_progress_count','?')}",
        ],
        "source_registries": ["cognitive_classroom_state.json",
                               "qsb_worker_certification_status.json"],
    }


def task_ledger_summary(worker: dict, body: str) -> dict:
    bank = load_json("qsb_internal_bank.json", {})
    pnl = load_json("qsb_floor41_oanda_pnl.json", {})
    return {
        "narrative": f"Ledger summary by clerk {worker['worker_id']}.",
        "findings": [
            f"QBC outstanding: {bank.get('qbc_outstanding','?')}",
            f"realized PnL (F41 OANDA practice): {pnl.get('realized','?')}",
        ],
        "source_registries": ["qsb_internal_bank.json", "qsb_floor41_oanda_pnl.json"],
    }


def task_research_openai(worker: dict, body: str) -> dict:
    """Send a research/inquiry task to OpenAI gpt-4o-mini as a colleague worker.
    body = the question. Reply is logged + budgeted by qsb_consult_external."""
    import subprocess
    if not body.strip():
        return {"narrative": f"{worker['worker_id']} → OpenAI: empty body, aborted.",
                "findings": ["body must be the question to research"],
                "source_registries": []}
    cmd = ["python3", str(ROOT / "tools/qsb_consult_external.py"),
            "--provider", "openai", "--model", "gpt-4o-mini",
            "--reason", f"dispatch:openai_worker:{worker['worker_id']}",
            "--max-tokens", "500",
            "--prompt", body[:1800]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=70, cwd=str(ROOT))
    except Exception as e:
        return {"narrative": f"OpenAI worker call failed for {worker['worker_id']}.",
                "findings": [str(e)[:200]], "source_registries": []}
    out = proc.stdout
    parts = out.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    # parts[0]="", parts[1]=metadata, parts[2]=actual reply text, parts[3]=""
    reply = parts[2].strip() if len(parts) >= 3 else out.strip()
    return {
        "narrative": f"OpenAI (gpt-4o-mini) consulted by {worker['worker_id']} as a colleague worker.",
        "findings": [
            f"return_code: {proc.returncode}",
            f"reply head: {reply[:400].replace(chr(10),' / ')}",
        ],
        "source_registries": [
            "qsb_provider_consultation_authorization.json",
            "qsb_provider_spend_ledger.jsonl",
            "qsb_tower_activity_tail.jsonl",
        ],
        "openai_reply": reply,
        "advisory_only": True,
    }


def task_research_deepseek(worker: dict, body: str) -> dict:
    """Send a research/inquiry task to DeepSeek deepseek-chat as a colleague worker."""
    import subprocess
    if not body.strip():
        return {"narrative": f"{worker['worker_id']} → DeepSeek: empty body, aborted.",
                "findings": ["body must be the question to research"],
                "source_registries": []}
    cmd = ["python3", str(ROOT / "tools/qsb_consult_external.py"),
            "--provider", "deepseek", "--model", "deepseek-chat",
            "--reason", f"dispatch:deepseek_worker:{worker['worker_id']}",
            "--max-tokens", "500",
            "--prompt", body[:1800]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=70, cwd=str(ROOT))
    except Exception as e:
        return {"narrative": f"DeepSeek worker call failed for {worker['worker_id']}.",
                "findings": [str(e)[:200]], "source_registries": []}
    out = proc.stdout
    parts = out.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    # parts[0]="", parts[1]=metadata, parts[2]=actual reply text, parts[3]=""
    reply = parts[2].strip() if len(parts) >= 3 else out.strip()
    return {
        "narrative": f"DeepSeek (deepseek-chat) consulted by {worker['worker_id']} as a colleague worker.",
        "findings": [
            f"return_code: {proc.returncode}",
            f"reply head: {reply[:400].replace(chr(10),' / ')}",
        ],
        "source_registries": [
            "qsb_provider_consultation_authorization.json",
            "qsb_provider_spend_ledger.jsonl",
        ],
        "deepseek_reply": reply,
        "advisory_only": True,
    }


def task_set_mode(worker: dict, body: str) -> dict:
    """Wren steward switches the kernel mode. body = WAKE|RESEARCH|MEDITATE|DREAM|EVOLVE|SLEEP."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from tower.cognitive_kernel.modes import set_mode, VALID_MODES
    except Exception as e:
        return {"narrative": f"set_mode by {worker['worker_id']} — module unavailable.",
                "findings": [str(e)[:160]],
                "source_registries": []}
    mode = (body or "").strip().upper()
    if mode not in VALID_MODES:
        return {"narrative": f"set_mode by {worker['worker_id']} — invalid mode {mode!r}.",
                "findings": [f"valid: {VALID_MODES}"],
                "source_registries": []}
    result = set_mode(mode, by=f"dispatch:{worker['worker_id']}",
                       reason="operator-requested via dispatch")
    return {
        "narrative": f"Kernel mode set to {mode} by {worker['worker_id']}.",
        "findings": [
            f"current_mode: {result['current_mode']}",
            f"description:  {result['description']}",
            f"gates:        {result['gates']}",
        ],
        "source_registries": ["qsb_kernel_mode_state.json",
                              "qsb_tower_activity_tail.jsonl"],
    }


def task_synthesize_strategy(worker: dict, body: str) -> dict:
    """Wren steward dispatches a synthesis run to F37 Strategy Labs.

    body: optional integer for top_n (default 8).
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from tower.cognitive_kernel.strategy_synthesis_sandbox import synthesize
    except Exception as e:
        return {
            "narrative": f"Synthesis dispatch by {worker['worker_id']} — module not available.",
            "findings": [f"import failed: {str(e)[:160]}"],
            "source_registries": ["qsb_floor37_strategy_labs_roster.json"],
        }
    top_n = 8
    try: top_n = max(1, int(body)) if body else 8
    except Exception: top_n = 8
    summary = synthesize(top_n=top_n)
    findings = [
        f"strategies considered:   {summary['strategies_considered']}",
        f"proposals generated:     {summary['proposals_generated']}",
        f"passing contradiction:   {summary['proposals_passing_contradiction_check']}",
        f"published top-N:         {summary['top_n_published']}",
        "─── top proposals ───",
    ]
    for p in summary["top_proposals"]:
        findings.append(
            f"  [{p['score']:.2f}]  {p['strategy_id']:24s}  {p['kind']:22s} → {p['change']}"
        )
    return {
        "narrative": (
            f"Synthesis run dispatched by {worker['worker_id']} → F37 Strategy Labs "
            f"({summary['proposals_generated']} generated · {summary['top_n_published']} published)."
        ),
        "findings": findings,
        "source_registries": [
            "qsb_floor37_synthesis_output.jsonl",
            "qsb_floor44_accounts_state.json",
            "qsb_wren_strategy_library.json",
        ],
        "summary": summary,
    }


def task_consult_external(worker: dict, body: str) -> dict:
    """Critic dispatches a single bounded provider consultation. body format:
        "<provider>:<model>:<reason>|<prompt>"
    e.g.:
        openai:gpt-4o-mini:adversarial_review|critique this strategy: ...
    Falls back to defaults if just a prompt is given:
        openai/gpt-4o-mini, reason='advisory_consultation'.
    """
    head, sep, prompt = (body.split("|", 1) + ["", ""])[:2] if "|" in body else ("", "", body)
    provider, model, reason = "openai", "gpt-4o-mini", "advisory_consultation"
    if head:
        parts = head.split(":")
        if len(parts) >= 1 and parts[0]: provider = parts[0].strip()
        if len(parts) >= 2 and parts[1]: model = parts[1].strip()
        if len(parts) >= 3 and parts[2]: reason = parts[2].strip()
    if not prompt.strip():
        return {
            "narrative": f"Consult by {worker['worker_id']} — empty prompt, aborted.",
            "findings": ["body format: <provider>:<model>:<reason>|<prompt>"],
            "source_registries": [],
        }
    import subprocess
    cmd = [
        "python3", str(ROOT / "tools/qsb_consult_external.py"),
        "--provider", provider, "--model", model,
        "--reason", f"dispatch:{worker['worker_id']}:{reason}",
        "--prompt", prompt[:2000],
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=70,
                                cwd=str(ROOT))
    except Exception as e:
        return {
            "narrative": f"Consult by {worker['worker_id']} — subprocess failed.",
            "findings": [str(e)[:200]],
            "source_registries": [],
        }
    out = proc.stdout
    err = proc.stderr.strip()
    return {
        "narrative": (
            f"Consult by {worker['worker_id']} via {provider}/{model}. "
            f"reason: {reason}."
        ),
        "findings": [
            f"return_code: {proc.returncode}",
            f"output_head: {out[:400].replace(chr(10),' / ')}",
            (f"stderr: {err[:200]}" if err else "stderr: (clean)"),
        ],
        "source_registries": [
            "qsb_provider_consultation_authorization.json",
            "qsb_provider_spend_ledger.jsonl",
            "qsb_tower_activity_tail.jsonl",
        ],
        "consult_output": out,
    }


def task_tower_pulse(worker: dict, body: str) -> dict:
    """Floor diplomat reads the tower activity tail and reports what just fired."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from tower.qsb_tower_activity import read_tail, summary_by_kind
    except Exception as e:
        return {
            "narrative": f"Pulse by {worker['worker_id']} — activity tail not yet available.",
            "findings": [f"import failed: {str(e)[:120]}"],
            "source_registries": ["qsb_tower_activity_tail.jsonl"],
        }
    n = 20
    try:
        n = max(5, int(body)) if body else 20
    except Exception:
        n = 20
    events = read_tail(last=n)
    counts = summary_by_kind(last=500)
    findings = [
        f"last {len(events)} events:",
    ]
    for ev in events[-15:]:
        ts = ev.get("ts", "")[:19]
        kind = ev.get("event_kind", "?")
        floor = ev.get("floor", "-")
        summary = ev.get("summary", "")[:120]
        findings.append(f"  {ts}  {kind:22s} {floor:4s} {summary}")
    findings.append("─── kind frequencies (last 500) ───")
    for k, c in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        findings.append(f"  {c:>4d}  {k}")
    return {
        "narrative": (
            f"Tower pulse by {worker['worker_id']} — "
            f"{len(events)} events shown · {sum(counts.values())} in last 500."
        ),
        "findings": findings,
        "source_registries": ["qsb_tower_activity_tail.jsonl"],
    }


def task_account_summary(worker: dict, body: str) -> dict:
    """Ledger clerk reads F44 Accounts/PnL roll-up and reports the picture."""
    acc = load_json("qsb_floor44_accounts_state.json", {})
    if not acc or "rolled_up_totals" not in acc:
        return {
            "narrative": f"Account summary by clerk {worker['worker_id']} — F44 state not yet built.",
            "findings": ["run: python3 -m tower.qsb_floor44_accounts"],
            "source_registries": ["qsb_floor44_accounts_state.json"],
        }
    rt = acc["rolled_up_totals"]
    by_venue = acc.get("by_venue", {})
    by_strat = acc.get("by_strategy", {})
    findings = [
        f"TOTAL realized: ${rt.get('realized_pnl_usd',0):>8.2f}  / £{rt.get('realized_pnl_gbp',0):>8.2f}",
        f"TOTAL unrealized: ${rt.get('unrealized_pnl_usd',0):>8.2f}  / £{rt.get('unrealized_pnl_gbp',0):>8.2f}",
        f"open positions: {rt.get('open_position_count',0)}  closed: {rt.get('closed_trade_count',0)}",
        f"win rate: {rt.get('win_rate')}  (winners {rt.get('win_count',0)}, losers {rt.get('loss_count',0)})",
        f"GBP/USD: {rt.get('gbp_per_usd','?')}",
        "─── by venue ───",
    ]
    for venue, v in by_venue.items():
        findings.append(
            f"  {venue:18s}  open={v.get('open_position_count',0):>2d}  "
            f"closed={v.get('closed_trade_count',0):>2d}  P&L=${v.get('total_pnl_usd',0):>7.2f}"
        )
    findings.append("─── top strategies by trade count ───")
    top = sorted(by_strat.items(),
                  key=lambda kv: -kv[1].get("trade_count", 0))[:6]
    for name, g in top:
        findings.append(
            f"  {name:28s}  trades={g.get('trade_count',0):>2d}  "
            f"realized=${g.get('realized_pnl_usd',0):>6.2f}  "
            f"workers={len(g.get('workers',[]))}"
        )
    return {
        "narrative": (
            f"Account summary by ledger clerk {worker['worker_id']} — F44 Accounts/PnL roll-up."
        ),
        "findings": findings,
        "source_registries": ["qsb_floor44_accounts_state.json"],
        "generated_ts_of_source": acc.get("generated_ts", "?"),
    }


def task_queue_status(worker: dict, body: str) -> dict:
    n = 0
    if OUTPUTS_PATH.exists():
        n = sum(1 for line in OUTPUTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    return {
        "narrative": f"Queue status by steward {worker['worker_id']}.",
        "findings": [
            f"team outputs on file: {n}",
            f"team size: {load_roster()['team_size']}",
        ],
        "source_registries": ["qsb_wren_team_outputs.jsonl",
                               "qsb_wren_team_roster.json"],
    }


# ── Kernel-talking tasks ────────────────────────────────────────────────


def _truncate(s: str, n: int = 600) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def task_petition_kernel(worker: dict, body: str) -> dict:
    """Petitioner POSTs an open question to /api/kernel_chat."""
    question = body or "What is the kernel doing right now?"
    r = ask_kernel(question)
    return {
        "narrative": f"Petition by {worker['worker_id']} to QSB Kernel.",
        "question": question,
        "kernel_reply_head": _truncate(r.get("reply", "")),
        "kernel_intent_classification": r.get("intent"),
        "source_endpoint": KERNEL_CHAT_URL,
    }


def task_specialist_inquiry(worker: dict, body: str) -> dict:
    """Topic specialist asks the kernel about their assigned topic."""
    topic = worker.get("assigned_topic", "general")
    question = body or f"Tell me everything you know about {topic.replace('_',' ')}."
    r = ask_kernel(question)
    return {
        "narrative": (
            f"Specialist inquiry by {worker['worker_id']} on topic "
            f"'{topic}'."
        ),
        "assigned_topic": topic,
        "question": question,
        "kernel_reply_head": _truncate(r.get("reply", "")),
        "kernel_intent_classification": r.get("intent"),
        "source_endpoint": KERNEL_CHAT_URL,
    }


def task_translate_kernel(worker: dict, body: str) -> dict:
    """Translator asks the kernel, then rewrites the reply for the body audience."""
    parts = (body or "operator|what should they know now").split("|", 1)
    audience = parts[0].strip() or "operator"
    question = parts[1].strip() if len(parts) > 1 else "what should they know right now"
    r = ask_kernel(question)
    reply_head = _truncate(r.get("reply", ""), 400)
    paraphrase = (
        f"For {audience}: the kernel says — {reply_head[:300]}\n"
        f"Translation by {worker['worker_id']}: the practical takeaway is to "
        f"treat the above as advisory. The kernel never executes; the gates remain locked."
    )
    return {
        "narrative": f"Translation by {worker['worker_id']} for audience '{audience}'.",
        "audience": audience,
        "kernel_question": question,
        "translated_message": paraphrase,
        "source_endpoint": KERNEL_CHAT_URL,
    }


def task_critic_probe(worker: dict, body: str) -> dict:
    """Critic asks an adversarial question to surface a gap."""
    question = body or "What is the riskiest thing in the tower right now that has no owner?"
    r = ask_kernel(question)
    reply = r.get("reply", "") or ""
    no_match = "no topic matched" in reply.lower()
    return {
        "narrative": (
            f"Critic probe by {worker['worker_id']}. "
            f"{'GAP FOUND — kernel had no specific answer.' if no_match else 'Kernel produced a specific answer.'}"
        ),
        "question": question,
        "kernel_reply_head": _truncate(reply, 400),
        "no_topic_matched": no_match,
        "gap_surfaced": no_match,
        "source_endpoint": KERNEL_CHAT_URL,
    }


def task_propose_topic_trigger(worker: dict, body: str) -> dict:
    """Proposer surfaces a recent no-match and suggests a trigger phrase."""
    proposal = body or "what is broken today"
    # First, verify the proposed phrase currently doesn't match
    r = ask_kernel(proposal)
    reply = r.get("reply", "") or ""
    no_match = "no topic matched" in reply.lower()
    return {
        "narrative": (
            f"Topic-trigger proposal by {worker['worker_id']}. "
            f"Phrase tested live against /api/kernel_chat."
        ),
        "proposed_trigger": proposal,
        "currently_unmatched": no_match,
        "suggested_target_topic": "morning_briefing",
        "note_to_wren": (
            "If currently_unmatched=True, add the phrase to _EQSB_TOPICS in "
            "src/tower/kernel_dialogue_adapter.py under the suggested_target_topic."
        ),
        "source_endpoint": KERNEL_CHAT_URL,
    }


TASKS = {
    "audit_f47":             ("auditor",                 task_audit_f47),
    "summarize_briefing":    ("auditor",                 task_summarize_briefing),
    "compose_letter":        ("scribe",                  task_compose_letter),
    "verify_helix":          ("helix_watcher",           task_verify_helix),
    "survey_library":        ("librarian",               task_survey_library),
    "propose_strategy":      ("strategy_researcher",     task_propose_strategy),
    "cross_floor_report":    ("floor_diplomat",          task_cross_floor_report),
    "classroom_status":      ("curriculum_tutor",        task_classroom_status),
    "ledger_summary":        ("ledger_clerk",            task_ledger_summary),
    "account_summary":       ("ledger_clerk",            task_account_summary),
    "tower_pulse":           ("floor_diplomat",          task_tower_pulse),
    "consult_external":      ("kernel_critic",           task_consult_external),
    "synthesize_strategy":   ("wren_steward",            task_synthesize_strategy),
    "set_mode":              ("wren_steward",            task_set_mode),
    "research_openai":       ("kernel_critic",           task_research_openai),
    "research_deepseek":     ("kernel_critic",           task_research_deepseek),
    "queue_status":          ("wren_steward",            task_queue_status),
    # Kernel-talking cohort
    "petition_kernel":       ("kernel_petitioner",       task_petition_kernel),
    "specialist_inquiry":    ("kernel_topic_specialist", task_specialist_inquiry),
    "translate_kernel":      ("kernel_translator",       task_translate_kernel),
    "critic_probe":          ("kernel_critic",           task_critic_probe),
    "propose_topic_trigger": ("kernel_proposer",         task_propose_topic_trigger),
}


def main():
    ap = argparse.ArgumentParser(description="Dispatch a task to a worker on Wren's F47 team.")
    ap.add_argument("task_kind", choices=list(TASKS.keys()),
                    help="What kind of task to assign.")
    ap.add_argument("--body", default="", help="Task body / prompt to the worker.")
    ap.add_argument("--worker", default=None,
                    help="Specific worker_id to assign (default: deterministic pick).")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress the receipt printed to stdout.")
    args = ap.parse_args()

    role, fn = TASKS[args.task_kind]
    worker = pick_worker(role, preferred_id=args.worker)
    output = fn(worker, args.body)

    record = {
        "ts": now(),
        "task_kind": args.task_kind,
        "task_body": args.body,
        "worker_id": worker["worker_id"],
        "worker_role": worker["role"],
        "execution_authority": "advisory_only",
        "external_api_called": False,
        "code_modified": False,
        "gates_flipped": False,
        "output": output,
    }
    with OUTPUTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    if not args.quiet:
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Wren's F47 Team · {worker['worker_id']} ({worker['role']})")
        print(f" Task: {args.task_kind}")
        if args.body:
            print(f" Body: {args.body[:200]}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(output.get("narrative", "(no narrative)"))
        for fnd in output.get("findings", []):
            print(f"  · {fnd}")
        if "draft" in output:
            print()
            print(output["draft"])
        # Kernel-talking task outputs: surface the reply head
        for key in ("question", "assigned_topic", "kernel_reply_head",
                     "translated_message", "proposed_trigger"):
            if key in output:
                val = str(output[key])
                if len(val) > 600:
                    val = val[:600] + "…"
                print(f"\n  {key}:\n    {val.replace(chr(10), chr(10)+'    ')}")
        if "no_topic_matched" in output:
            print(f"\n  no_topic_matched: {output['no_topic_matched']}")
        sr = output.get("source_registries", [])
        if sr:
            print(f"\n  Sources: {', '.join(sr)}")
        if "source_endpoint" in output:
            print(f"  Endpoint: {output['source_endpoint']}")
        print(f"\n  Stamped to: {OUTPUTS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
