"""Stale sim/sandbox language audit — surfaces user-facing leaks of legacy terms."""

from datetime import datetime, timezone
from pathlib import Path
import re

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")

LIVE_UI_SCAN = [
    ROOT / "src/dashboard/server.py",
    ROOT / "src/dashboard/static/cockpit.js",
    ROOT / "src/dashboard/static/cockpit.css",
    ROOT / "src/dashboard/static/index.html",
    ROOT / "src/dashboard/static/qsb_scene.js",
    ROOT / "src/dashboard/static/qsb_tower_2d.js",
    ROOT / "src/dashboard/static/qsb_floor_interior.js",
    ROOT / "src/dashboard/static/qsb_windows.js",
    ROOT / "src/dashboard/static/qsb_state.js",
    ROOT / "src/dashboard/static/qsb_audio.js",
]

STALE_PATTERNS = [
    (r"\bsim_worker\b",            "sim_worker"),
    (r"\bworker_sandbox\b",        "worker_sandbox"),
    (r"\bsandbox_to_risk\b",       "sandbox_to_risk"),
    (r"\bstrategy_to_sandbox\b",   "strategy_to_sandbox"),
    (r"paper-only research",       "paper-only research"),
    (r"\bsandbox\b",               "sandbox"),
]

PREFERRED_NAMES = {
    "sim_worker":         "worker / display_name",
    "worker_sandbox":     "worker_operations",
    "sandbox_to_risk":    "worker_ops_to_risk",
    "strategy_to_sandbox":"strategy_to_worker_ops",
    "paper-only research":"practice telemetry / advisory analysis",
    "sandbox":            "practice / training / worker operations",
}


def _now(): return datetime.now(timezone.utc).isoformat()


def stale_language_audit():
    findings = []
    for fp in LIVE_UI_SCAN:
        if not fp.exists(): continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        per_file = []
        for pat, lex in STALE_PATTERNS:
            hits = len(re.findall(pat, text))
            if hits:
                per_file.append({"term": lex, "hits": hits,
                                 "preferred": PREFERRED_NAMES.get(lex)})
        if per_file:
            findings.append({"file": str(fp), "hits": per_file,
                             "total_hits": sum(h["hits"] for h in per_file)})
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "STALE_LANGUAGE_AUDIT",
        "scanned_files": [str(p) for p in LIVE_UI_SCAN if p.exists()],
        "findings": findings,
        "files_with_hits": len(findings),
        "execution_allowed": False,
    })


def clean_stale_language(payload=None):
    """Report what *would* be cleaned. Does NOT mutate JS/CSS during V1.5 —
    Ross's brief said to replace user-facing labels carefully, and the V1.5
    correction loop is restricted to safe-non-destructive edits. This endpoint
    returns the recommended rewrites only.
    """
    audit = stale_language_audit()
    recommendations = []
    for finding in (audit.get("findings") or []):
        for hit in finding.get("hits") or []:
            recommendations.append({
                "file":     finding["file"],
                "replace":  hit["term"],
                "with":     hit["preferred"],
                "hits":     hit["hits"],
            })
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "STALE_LANGUAGE_CLEAN_RECOMMENDATIONS",
        "recommendations": recommendations,
        "applied_changes": [],
        "note": ("V1.5 correction loop reports recommended rewrites. "
                  "Apply with manual edit only — automated replace would risk "
                  "breaking JS identifiers."),
        "execution_allowed": False,
    })
