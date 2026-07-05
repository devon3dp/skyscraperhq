#!/usr/bin/env python3
"""qsb_proposal_applier.py — the final step of the bench.

Turns a "ready" proposal (≥3 sigs, sandbox green, gate enabled, safety-clear)
into an actual file mutation. Writes an audit row for every apply.

Supported concrete_change operations (v1, conservative):
  · merge_dict       — merge values into a nested dict in a JSON registry
  · set_json_path    — set a single value at a dotted path in JSON
  · review_only      — no file mutation; just mark applied
  · trigger_run      — no file mutation; just stamps an audit row

Anything else: refuses to apply. Logs reason.
"""
from __future__ import annotations
import json, sys, hashlib, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
APPLY_AUDIT = ROOT / "data/registries/qsb_code_apply_audit.jsonl"
SANDBOX_RES = ROOT / "data/registries/qsb_proposal_sandbox_results.jsonl"
GATE = ROOT / "data/registries/qsb_proposal_autoapply_gate.json"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"

SAFETY_PATHS = (
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    "tools/qsb_oanda.py",
    "src/tower/qsb_floor41_oanda",
    ".env",
    "data/registries/qsb_proposal_autoapply_gate.json",
)

SIG_THRESHOLD = 3
APPROVER_CLASSES = ("coders_team", "team_assistants", "wren_crew",
                    "wren_herself", "ross")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gate_on() -> bool:
    if not GATE.exists():
        return False
    try:
        return bool(json.loads(GATE.read_text()).get("enabled", False))
    except Exception:
        return False


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


def count_sigs(p: dict) -> int:
    return len({s.get("approver_class") for s in p.get("sigs", [])
                if s.get("approver_class") in APPROVER_CLASSES})


def sandbox_green_for(pid: str) -> bool:
    if not SANDBOX_RES.exists():
        return False
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
    return (latest or {}).get("verdict") == "green"


def file_sha(p: Path) -> str:
    if not p.exists():
        return ""
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()[:16]


# ── apply operations ─────────────────────────────────────────────────

def op_merge_dict(p: dict) -> tuple[bool, str]:
    """concrete_change = {operation: merge_dict, into: <key>, values: {...}}"""
    cc = p.get("concrete_change", {})
    into_key = cc.get("into")
    values = cc.get("values", {})
    if not into_key or not isinstance(values, dict):
        return False, "missing_into_or_values"
    targets = p.get("target_files", [])
    if not targets:
        return False, "no_target_file"
    target_path = ROOT / targets[0]
    if not target_path.exists():
        return False, f"target_missing:{targets[0]}"
    try:
        data = json.loads(target_path.read_text())
    except Exception as e:
        return False, f"json_parse:{str(e)[:80]}"
    if into_key not in data or not isinstance(data[into_key], dict):
        return False, f"into_key_not_dict:{into_key}"
    before = len(data[into_key])
    data[into_key].update(values)
    after = len(data[into_key])
    target_path.write_text(json.dumps(data, indent=2))
    return True, f"merged {after-before} new entries into {into_key} ({before}→{after})"


def op_set_css_var(p: dict) -> tuple[bool, str]:
    """concrete_change = {css_var: '--qsb-bg', to: '#0a1422'} — append at end."""
    cc = p.get("concrete_change", {})
    var = cc.get("css_var")
    to = cc.get("to")
    if not var or not to:
        return False, "missing_var_or_to"
    targets = p.get("target_files", [])
    if not targets:
        return False, "no_target_file"
    # Apply to first CSS target only
    css_target = None
    for t in targets:
        if t.endswith(".css"):
            css_target = ROOT / t
            break
    if not css_target or not css_target.exists():
        return False, "no_css_target_found"
    src = css_target.read_text()
    marker = f"\n/* F47 bench applied {utcnow()} — {var} */\n:root {{ {var}: {to}; }}\n"
    if marker.strip() in src:
        return False, "already_applied"
    css_target.write_text(src + marker)
    return True, f"appended :root {{ {var}: {to}; }} to {css_target.name}"


def apply_one(p: dict) -> dict:
    pid = p.get("id") or p.get("ts")
    if p.get("applied"):
        return {"applied": False, "reason": "already_applied"}
    if not gate_on():
        return {"applied": False, "reason": "gate_off"}
    if is_safety_flagged(p):
        return {"applied": False, "reason": "safety_path"}
    if count_sigs(p) < SIG_THRESHOLD:
        return {"applied": False, "reason": f"insufficient_sigs:{count_sigs(p)}"}
    if not sandbox_green_for(pid):
        return {"applied": False, "reason": "sandbox_not_green"}

    kind = p.get("kind")
    cc = p.get("concrete_change", {})

    # review-only / trigger-only kinds: mark applied without file change
    if kind in ("catalog_quality_report", "todo_audit_report",
                "broken_import_report", "trigger_graphics_run"):
        return {"applied": True, "reason": "review_only_marked"}

    # dispatch by operation
    op = cc.get("operation")
    if op == "merge_dict":
        ok, detail = op_merge_dict(p)
    elif kind == "css_palette_proposal":
        ok, detail = op_set_css_var(p)
    else:
        return {"applied": False, "reason": f"no_applier_for:{kind}/{op}"}

    return {"applied": ok, "reason": detail}


def main():
    rows = read_proposals()
    applied = []
    refused = []
    for i, p in enumerate(rows):
        if p.get("applied"):
            continue
        pid = p.get("id") or p.get("ts")
        targets = p.get("target_files", [])
        sha_before = {t: file_sha(ROOT / t) for t in targets}
        verdict = apply_one(p)
        sha_after = {t: file_sha(ROOT / t) for t in targets}
        rec = {
            "ts": utcnow(),
            "proposal_id": pid,
            "kind": p.get("kind"),
            "target_files": targets,
            "sigs": [s.get("approver_class") for s in p.get("sigs", [])],
            "sandbox_green": sandbox_green_for(pid),
            "applier": "qsb_proposal_applier",
            "sha_before": sha_before,
            "sha_after": sha_after,
            **verdict,
        }
        with APPLY_AUDIT.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        if verdict["applied"]:
            p["applied"] = True
            p["applied_ts"] = utcnow()
            applied.append({"id": pid, "kind": p.get("kind"),
                             "detail": verdict["reason"]})
        else:
            refused.append({"id": pid, "reason": verdict["reason"]})

    if applied:
        write_proposals(rows)

    rec = {
        "ts": utcnow(),
        "kind": "applier_tick",
        "floor": "F47",
        "operator": "background",
        "executed_by": "f47.proposal_applier",
        "applied_count": len(applied),
        "applied": applied,
        "refused_count": len(refused),
        "refused_sample": refused[:8],
    }
    with F47_REC.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
