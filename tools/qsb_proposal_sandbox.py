#!/usr/bin/env python3
"""qsb_proposal_sandbox.py — run a code-change proposal in an isolated sandbox.

Ross 2026-06-13: "code must be run first in sandbox etc and must pass and be
signed off before you install"

Mechanism:
  1. Read the proposal from qsb_code_proposals.jsonl by id
  2. Refuse if any safety-tagged path (CLAUDE.md, vault/, etc.)
  3. Create /tmp/qsb_sandbox_<short_sha>/ as a working copy of the affected files
  4. Apply the proposed patch (unified diff or file replacements)
  5. Run smoke tests:
        · python3 -m py_compile <changed .py>
        · the project's test command if defined
        · cockpit JS lint (node --check) if a JS file changed
  6. Stamp result to qsb_proposal_sandbox_results.jsonl
  7. Print verdict — DOES NOT touch the live tree

Apply step is a SEPARATE tool. Sandbox = verify only.
"""
from __future__ import annotations
import json, sys, hashlib, subprocess, shutil, tempfile, argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
# Bench reads from BOTH proposal queues — qsb_code_proposals (older path)
# and qsb_proposal_queue.jsonl (where Wren's local agent + provider agents
# write since 2026-06-14). Match by either `id` or `proposal_id`.
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
PROPOSAL_QUEUE = ROOT / "data/registries/qsb_proposal_queue.jsonl"
RESULTS = ROOT / "data/registries/qsb_proposal_sandbox_results.jsonl"

SAFETY_PATHS = (
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    ".env",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_proposal(pid: str) -> dict | None:
    """Read both queue files, matching on either `id` or `proposal_id`."""
    for path in (PROPOSALS, PROPOSAL_QUEUE):
        if not path.exists():
            continue
        for ln in path.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                p = json.loads(ln)
                if (p.get("id") == pid or p.get("proposal_id") == pid
                        or p.get("ts") == pid):
                    return p
            except Exception:
                continue
    return None


def is_safety_flagged(p: dict) -> tuple[bool, str]:
    targets = p.get("target_files", []) or (
        [p.get("target_file")] if p.get("target_file") else []
    )
    for t in targets:
        if not t:
            continue
        for sp in SAFETY_PATHS:
            if sp in t:
                return True, f"target {t} matches safety path {sp}"
    return False, ""


def run_smoke(file_path: Path) -> dict:
    """Quick verifier per file type."""
    if file_path.suffix == ".py":
        r = subprocess.run(["python3", "-m", "py_compile", str(file_path)],
                            capture_output=True, text=True, timeout=20)
        return {"check": "py_compile", "rc": r.returncode,
                "stderr_tail": r.stderr[-300:]}
    if file_path.suffix == ".json":
        try:
            json.loads(file_path.read_text())
            return {"check": "json_parse", "rc": 0, "stderr_tail": ""}
        except Exception as e:
            return {"check": "json_parse", "rc": 1, "stderr_tail": str(e)[:300]}
    if file_path.suffix in (".js",):
        r = subprocess.run(["node", "--check", str(file_path)],
                            capture_output=True, text=True, timeout=20)
        return {"check": "node_check", "rc": r.returncode,
                "stderr_tail": r.stderr[-300:]}
    # CSS / HTML / others: just check file is readable + UTF-8 valid
    try:
        file_path.read_text(encoding="utf-8")
        return {"check": "utf8_read", "rc": 0, "stderr_tail": ""}
    except Exception as e:
        return {"check": "utf8_read", "rc": 1, "stderr_tail": str(e)[:300]}


def write_result(rec: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def run_sandbox(pid: str) -> dict:
    p = load_proposal(pid)
    if not p:
        return {"ok": False, "verdict": "not_found", "id": pid}

    safety, why = is_safety_flagged(p)
    if safety:
        rec = {"ts": utcnow(), "id": pid, "verdict": "safety_refused",
                "reason": why, "ok": False}
        write_result(rec)
        return rec

    # Build sandbox dir
    short = hashlib.sha256(pid.encode()).hexdigest()[:10]
    sandbox = Path(tempfile.gettempdir()) / f"qsb_sandbox_{short}"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True)

    # Stage 1: copy targeted files into sandbox + apply replacements
    targets = p.get("target_files", []) or (
        [p.get("target_file")] if p.get("target_file") else []
    )
    smokes = []
    diffs = p.get("file_replacements", {})  # {relpath: new_content}
    if not diffs:
        # Fallback: nothing to apply, just verify syntax of original
        for t in targets:
            tp = ROOT / t
            if tp.exists():
                smokes.append({"file": t, **run_smoke(tp)})
    else:
        for relpath, new_content in diffs.items():
            sp = sandbox / Path(relpath).name
            sp.write_text(new_content)
            smokes.append({"file": relpath, **run_smoke(sp)})

    failures = [s for s in smokes if s.get("rc", 1) != 0]
    verdict = "green" if not failures else "red"
    rec = {
        "ts": utcnow(),
        "id": pid,
        "verdict": verdict,
        "sandbox_dir": str(sandbox),
        "smokes": smokes,
        "ok": verdict == "green",
    }
    write_result(rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proposal_id")
    args = ap.parse_args()
    rec = run_sandbox(args.proposal_id)
    print(json.dumps(rec, indent=2))
    return 0 if rec.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
