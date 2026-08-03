#!/usr/bin/env python3
"""qsb_auto_sigs.py — sandbox + conservative auto-sig loop.

Ross 2026-06-13: "wire auto sig etc"

For each new proposal (unsigned, unapplied):
  1. If not yet sandboxed → run qsb_proposal_sandbox.py (single attempt)
  2. If sandbox = green AND proposal meets conservative auto-sig criteria
     → add sigs from wren_crew + team_assistants
  3. If sandbox = red → refuse, log refusal note

CONSERVATIVE allow-list (v1) — auto-sig ONLY when:
  · the proposal is registry-extension (additive, non-destructive)
    OR cosmetic CSS palette tweak
  · target paths outside SAFETY_PATHS
  · proposal has a "reason" field with >= 40 chars
  · proposal has a concrete_change field

Anything else: NOT auto-signed. Sits in queue waiting for Ross/Wren.
"""
from __future__ import annotations
import json, sys, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
SANDBOX_RES = ROOT / "data/registries/qsb_proposal_sandbox_results.jsonl"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"

SAFETY_PATHS = (
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    "tools/qsb_oanda.py",
    "src/tower/qsb_floor41_oanda",
    "oanda",  # 2026-08-03: broaden — ANY oanda path (real-money broker) refused,
              # and align this list with the applier's (was missing the oanda paths).
    ".env",
    "data/registries/qsb_proposal_autoapply_gate.json",
)

AUTO_SIG_KINDS = {
    "css_palette_proposal",
    "registry_extension_proposal",
    "trigger_graphics_run",          # read-only, just kicks the crew
    "catalog_quality_report",        # review-only flag, no patch
    "todo_audit_report",              # review-only flag, no patch
    "broken_import_report",          # review-only flag
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_proposals() -> list[dict]:
    if not PROPOSALS.exists():
        return []
    out = []
    for ln in PROPOSALS.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def write_proposals(rows: list[dict]) -> None:
    PROPOSALS.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def is_safety_flagged(p: dict) -> bool:
    targets = p.get("target_files", []) or []
    for t in targets:
        for sp in SAFETY_PATHS:
            if sp in (t or ""):
                return True
    return False


REVIEW_ONLY_KINDS = (
    "catalog_quality_report", "todo_audit_report",
    "broken_import_report", "trigger_graphics_run",
)


def _coders_team_ok(p: dict) -> tuple[bool, str]:
    """3rd-pass review for the coders_team class.

    Ross 2026-06-14: authorized "yes" to flip auto-sign for the bigger kinds
    too — registry_extension + css_palette no longer need size guards.
    Safety is still upheld by: sandbox-green requirement, SAFETY_PATHS refusal
    (CLAUDE.md, vault/, .env, gate.json, OANDA/consult tools), and the
    kill switch (qsb_proposal_autoapply_gate.json enabled=false).

      · review-only kinds with empty target_files → safe, sign
      · registry_extension with any values dict → sign (sandbox already verified)
      · css_palette with css_var + to → sign (cosmetic, sandbox verified)
      · anything else → refuse, leave for ross/wren_herself manual sign
    """
    kind = p.get("kind")
    cc = p.get("concrete_change", {}) or {}
    targets = p.get("target_files", []) or []
    # Review/trigger proposals are non-mutating even when they carry a target
    # registry for attribution. They are safe for the third review signature;
    # the applier only records them as completed and performs no file change.
    if kind in REVIEW_ONLY_KINDS:
        return True, f"review_only:{kind}"
    if kind == "registry_extension_proposal":
        vals = cc.get("values", {})
        if isinstance(vals, dict) and len(vals) > 0:
            return True, f"registry_extension ({len(vals)} keys, sandbox green)"
        return False, "registry_extension missing values"
    if kind == "css_palette_proposal":
        if cc.get("css_var") and cc.get("to"):
            return True, f"css_palette {cc.get('css_var')} → {cc.get('to')}"
        return False, "css_palette missing css_var or to"
    return False, f"coders_team holds for {kind} — needs ross or wren_herself sign"


def passes_auto_sig_criteria(p: dict) -> tuple[bool, str]:
    if p.get("applied"):
        return False, "already_applied"
    if is_safety_flagged(p):
        return False, "safety_path"
    if p.get("kind") not in AUTO_SIG_KINDS:
        return False, f"kind_not_in_allow_list:{p.get('kind')}"
    if len((p.get("reason") or "")) < 40:
        return False, "reason_too_short"
    if not p.get("concrete_change"):
        return False, "no_concrete_change"
    return True, "ok"


def sandbox_verdict_for(pid: str) -> str | None:
    if not SANDBOX_RES.exists():
        return None
    latest = None
    for ln in SANDBOX_RES.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("id") == pid:
            latest = r
    return (latest or {}).get("verdict")


def run_sandbox(pid: str) -> str | None:
    r = subprocess.run(["python3", "tools/qsb_proposal_sandbox.py", pid],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    return sandbox_verdict_for(pid)


def add_sig(p: dict, klass: str, who: str, note: str = "") -> dict:
    sigs = p.setdefault("sigs", [])
    if any(s.get("approver_class") == klass for s in sigs):
        return p  # already signed by this class
    sigs.append({
        "ts": utcnow(),
        "approver_class": klass,
        "approver_id": who,
        "note": note,
    })
    return p


def main():
    rows = read_proposals()
    pending = [r for r in rows if not r.get("applied")]

    actions = {"sandboxed": 0, "auto_signed": 0,
                "refused_sandbox_red": 0, "refused_criteria": 0}
    refusals = []

    for p in pending:
        pid = p.get("id") or p.get("ts")
        ok, why = passes_auto_sig_criteria(p)
        if not ok:
            # log as refused (not auto-signed) but leave for Ross
            actions["refused_criteria"] += 1
            refusals.append({"id": pid, "reason": why})
            continue

        # ensure sandbox has run
        verdict = sandbox_verdict_for(pid)
        if verdict is None:
            verdict = run_sandbox(pid)
            actions["sandboxed"] += 1

        if verdict != "green":
            actions["refused_sandbox_red"] += 1
            refusals.append({"id": pid, "reason": f"sandbox_{verdict}"})
            continue

        # Auto-sig: wren_crew + team_assistants + coders_team = 3 of 3 needed.
        # Each class represents a distinct review pass — see _coders_team_ok
        # for the additional stricter check the 3rd class runs.
        # Ross 2026-06-14: "fix the sandbox and the multi sig path".
        # The 4th + 5th sig classes (wren_herself, ross) stay manual: a
        # higher-stakes proposal can still be held back if coders_team refuses
        # via _coders_team_ok returning False.
        existing_classes = {s.get("approver_class") for s in p.get("sigs", [])}
        if "wren_crew" not in existing_classes:
            add_sig(p, "wren_crew", "f47.audit_crew.peer_review",
                    f"auto-signed: kind={p.get('kind')}, sandbox=green, "
                    f"reason_len={len(p.get('reason',''))}")
        if "team_assistants" not in existing_classes:
            add_sig(p, "team_assistants", "f47.audit_crew.assistant_review",
                    "auto-signed: criteria met, sandbox green")
        if "coders_team" not in existing_classes:
            ok_ct, ct_note = _coders_team_ok(p)
            if ok_ct:
                add_sig(p, "coders_team", "f47.coders_team.review_bot",
                        f"auto-signed: {ct_note}")
        actions["auto_signed"] += 1

    write_proposals(rows)

    rec = {
        "ts": utcnow(),
        "kind": "auto_sigs_tick",
        "floor": "F47",
        "operator": "background",
        "executed_by": "f47.auto_sigs_loop",
        "queue_depth_pending": len(pending),
        "actions": actions,
        "refusals_sample": refusals[:8],
    }
    with F47_REC.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
