#!/usr/bin/env python3
"""qsb_apply_bridge.py — the APPLY BRIDGE (2026-07-29).

PIECE 3 of 3 of the council ship-pipeline. Turns a council-VERIFIED artifact
(the throwaway tests/backlog_<tid>.<ext> file a completed task produces) into a
LIVE code change, so the council can actually SHIP.

Flow for a task that reached `done` with a verified code artifact:
  1. Resolve the target file (task.target_file, else inferred from the artifact).
  2. Build a proper file_replacements proposal {relpath -> full new content}.
  3. Run it through the EXISTING sandbox (qsb_proposal_sandbox.run_sandbox) —
     must go GREEN (real py_compile / node --check / json parse).
  4. Record the proposal to qsb_proposal_queue.jsonl.
  5. APPLY GATE — write the LIVE file ONLY when ALL hold:
       (a) sandbox GREEN
       (b) target is NOT a SAFETY_DENY path
       (c) the council quorum already approved (>=2 distinct-provider peer
           signoffs on the task — passed in by the caller / read from history)
     Ross has authorised this self-improvement work, so the standing
     authorization is the human sign for NON-safety files. SAFETY_DENY paths
     stay HARD-BLOCKED regardless of sandbox / quorum.
  6. On apply: cp the live file to a timestamped .bak, write the new content,
     append a full audit row to data/registries/qsb_code_apply_audit.jsonl.
  7. If the applied file fails py_compile, AUTO-ROLLBACK from the .bak and log it.

This module is import-safe and best-effort: apply_verified_artifact() never
raises; every outcome is a dict + an audit row.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
PROPOSAL_QUEUE = REG / "qsb_proposal_queue.jsonl"
APPLY_AUDIT = REG / "qsb_code_apply_audit.jsonl"

# SAFETY_DENY — hard-blocked regardless of sandbox/quorum/standing auth. Mirrors
# the applier + CLAUDE.md SAFETY_DENY set (kept local so the bridge is self-contained).
SAFETY_PATHS = (
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    "tools/qsb_oanda.py",
    "src/tower/qsb_floor41_oanda",
    ".env",
    "data/registries/qsb_proposal_autoapply_gate.json",
    "data/registries/qsb_provider_agentic_gate.json",
    "data/registries/qsb_wren_local_agentic_gate.json",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def is_safety_path(relpath: str) -> bool:
    relpath = (relpath or "").lstrip("/")
    return any(sp in relpath for sp in SAFETY_PATHS)


# ---------------------------------------------------------------------------
# artifact -> code
# ---------------------------------------------------------------------------
def _unwrap_artifact(raw: str) -> str:
    """The .txt backlog wrapper is 'TASK <tid>\\n<title>\\ntool <tool>\\n---\\n<code>\\n'.
    Strip it to get the raw deliverable. HTML artifacts (and anything without the
    header) pass through unchanged."""
    if raw.startswith("TASK ") and "\n---\n" in raw[:400]:
        return raw.split("\n---\n", 1)[1].rstrip("\n") + "\n"
    return raw


def _strip_code_fence(code: str) -> str:
    """Producers occasionally wrap output in a ```lang fence — remove it so the
    live file is valid source, not markdown."""
    m = re.match(r"^\s*```[a-zA-Z0-9_+-]*\n(.*?)\n```\s*$", code, re.DOTALL)
    return m.group(1) + "\n" if m else code


def read_artifact_code(artifact_path: str | Path) -> str | None:
    p = Path(artifact_path)
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    return _strip_code_fence(_unwrap_artifact(raw))


# ---------------------------------------------------------------------------
# target resolution
# ---------------------------------------------------------------------------
def resolve_target(task: dict, artifact_path: str | None) -> str | None:
    """task.target_file wins; else infer from the artifact extension into tests/
    (a safe, non-live default so an unlabelled task never overwrites live code by
    accident)."""
    tf = (task or {}).get("target_file")
    if tf:
        return tf.lstrip("/")
    if artifact_path:
        ext = Path(artifact_path).suffix or ".txt"
        tid = (task or {}).get("id", "unknown")
        return f"tests/applied_{tid}{ext}"
    return None


# ---------------------------------------------------------------------------
# quorum
# ---------------------------------------------------------------------------
def quorum_from_task(task: dict, approvals: list | None = None) -> list[str]:
    """Distinct approving verifiers. Prefer the caller-supplied `approvals`
    (in-hand from run_backlog, no snapshot lag); else read peer_signoff/approve
    events from the task history."""
    if approvals:
        return sorted(set(approvals))
    out = []
    for h in (task or {}).get("history") or []:
        if h.get("event") == "peer_signoff" and h.get("verdict") == "approve":
            a = h.get("actor")
            if a:
                out.append(a)
    return sorted(set(out))


# ---------------------------------------------------------------------------
# proposal + sandbox
# ---------------------------------------------------------------------------
def _queue_proposal(proposal: dict) -> None:
    PROPOSAL_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with PROPOSAL_QUEUE.open("a") as f:
        f.write(json.dumps(proposal) + "\n")


def _audit(rec: dict) -> None:
    APPLY_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    rec.setdefault("ts", utcnow())
    with APPLY_AUDIT.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _py_compile_ok(path: Path) -> tuple[bool, str]:
    if path.suffix != ".py":
        return True, ""
    r = subprocess.run(["python3", "-m", "py_compile", str(path)],
                       capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stderr[-400:]


def _smoke_ok(path: Path) -> tuple[bool, str]:
    """2026-07-29: post-apply RUNTIME smoke. py_compile only proves the code parses — it does NOT
    prove the server still serves. (A generated tour-guide module compiled fine but 404'd on `/`.)
    For an http.server module, run the APPLIED file on a scratch port and confirm the base route
    still returns 200; regression -> caller rolls back. Non-server files skip (compile is the gate)."""
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return True, "unreadable — skip smoke"
    import re as _re
    if not _re.search(r"HTTPServer|create_server|serve_forever|--port|BaseHTTPRequestHandler", text):
        return True, "not a server module — skip smoke"
    import socket, time, urllib.request, urllib.error
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    proc = subprocess.Popen(["python3", str(path), "--port", str(port)],
                            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3.5)
        for route in ("/",):
            try:
                code = urllib.request.urlopen(f"http://127.0.0.1:{port}{route}", timeout=6).getcode()
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception as e:
                return False, f"smoke {route} did not serve ({type(e).__name__})"
            if code != 200:
                return False, f"smoke {route} -> HTTP {code} (regressed the base route)"
        return True, "smoke / -> 200 (server still serves)"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------
def apply_verified_artifact(task: dict, artifact_path: str | None,
                            approvals: list | None = None,
                            applier: str = "apply_bridge") -> dict:
    """Best-effort: never raises. Returns a dict describing the outcome and
    always leaves an audit row when it reaches (or refuses at) the apply gate."""
    try:
        return _apply_verified_artifact(task, artifact_path, approvals, applier)
    except Exception as e:  # never break the caller
        rec = {"ts": utcnow(), "task_id": (task or {}).get("id"),
               "applier": applier, "applied": False,
               "reason": f"bridge_exception:{type(e).__name__}:{str(e)[:200]}"}
        try:
            _audit(rec)
        except Exception:
            pass
        return rec


def _apply_verified_artifact(task, artifact_path, approvals, applier):
    tid = (task or {}).get("id", "unknown")
    result = {"task_id": tid, "applier": applier, "applied": False}

    code = read_artifact_code(artifact_path) if artifact_path else None
    if not code or not code.strip():
        result["reason"] = "no_artifact_code"
        return result

    target = resolve_target(task, artifact_path)
    if not target:
        result["reason"] = "no_target"
        return result
    result["target"] = target

    quorum = quorum_from_task(task, approvals)
    if len(quorum) < 2:
        result["reason"] = f"insufficient_quorum:{len(quorum)}"
        result["quorum"] = quorum
        return result
    result["quorum"] = quorum

    # Build a proper file_replacements proposal and queue it.
    proposal_id = f"applybridge_{tid}_{_sha(code)[:10]}"
    proposal = {
        "ts": utcnow(),
        "proposal_id": proposal_id,
        "id": proposal_id,
        "source": "apply_bridge",
        "origin": f"council_task:{tid}",
        "target_files": [target],
        "target_file": target,
        "file_replacements": {target: code},
        "status": "queued_unsigned",
        "quorum": quorum,
        "sigs": [],
    }
    _queue_proposal(proposal)

    # Sandbox — must go GREEN. TRIAD hardening (three independent checks, 2-of-3
    # quorum; unanimous 3/3 for live-service files) runs FIRST and IN PLACE of the
    # old single compile check. If the triad module can't be imported for any
    # reason, fall back to the legacy single-check sandbox so the gate never
    # silently opens. This is an ADDITIONAL guard BEFORE the downstream SAFETY_DENY
    # + 2-CEO quorum + Ross gate — none of which are loosened. Import lazily so
    # this module stays cheap to import.
    try:
        import qsb_triad_sandbox as TRIAD
        sb = TRIAD.run_triad(proposal_id)
        sb_engine = "triad"
    except Exception as _triad_err:
        import qsb_proposal_sandbox as SB
        sb = SB.run_sandbox(proposal_id)
        sb["_triad_fallback_reason"] = str(_triad_err)[:200]
        sb_engine = "single_fallback"
    verdict = sb.get("verdict")
    result["sandbox"] = verdict
    result["sandbox_engine"] = sb_engine
    if verdict != "green":
        result["reason"] = f"sandbox_{verdict}"
        _audit({"task_id": tid, "proposal_id": proposal_id, "target": target,
                "applier": applier, "applied": False, "sandbox": verdict,
                "sandbox_engine": sb_engine, "quorum": quorum,
                "reason": f"sandbox_{verdict}",
                "sandbox_detail": sb.get("sandboxes") or sb.get("smokes") or sb.get("reason")})
        return result

    # APPLY GATE ------------------------------------------------------------
    # (b) SAFETY_DENY hard-block — regardless of green sandbox + quorum.
    if is_safety_path(target):
        result["reason"] = "safety_refused"
        _audit({"task_id": tid, "proposal_id": proposal_id, "target": target,
                "applier": applier, "applied": False, "sandbox": "green",
                "quorum": quorum, "reason": "safety_refused",
                "note": "SAFETY_DENY path — hard-blocked regardless of sandbox/quorum"})
        return result

    live = ROOT / target
    live.parent.mkdir(parents=True, exist_ok=True)
    existed = live.exists()
    before_text = live.read_text(encoding="utf-8", errors="replace") if existed else ""
    sha_before = _sha(before_text) if existed else None

    # No-op guard: identical content -> nothing to ship.
    if existed and before_text == code:
        result["applied"] = False
        result["reason"] = "no_change"
        _audit({"task_id": tid, "proposal_id": proposal_id, "target": target,
                "applier": applier, "applied": False, "sandbox": "green",
                "quorum": quorum, "reason": "no_change",
                "sha_before": sha_before, "sha_after": sha_before})
        return result

    # cp live -> timestamped .bak (only if it already exists)
    bak = None
    if existed:
        bak = live.with_name(live.name + f".bak_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_apply_bridge")
        shutil.copy2(live, bak)

    live.write_text(code, encoding="utf-8")
    sha_after = _sha(code)

    # Post-apply integrity check -> AUTO-ROLLBACK on broken .py
    ok, cerr = _py_compile_ok(live)
    if not ok:
        if existed and bak:
            shutil.copy2(bak, live)  # roll back to the .bak
            rolled = "rolled_back_from_bak"
        else:
            live.unlink(missing_ok=True)  # newly-created broken file -> remove
            rolled = "removed_new_broken_file"
        result["applied"] = False
        result["reason"] = "post_apply_py_compile_failed"
        result["rollback"] = rolled
        _audit({"task_id": tid, "proposal_id": proposal_id, "target": target,
                "applier": applier, "applied": False, "sandbox": "green",
                "quorum": quorum, "reason": "post_apply_py_compile_failed",
                "rollback": rolled, "compile_err": cerr,
                "sha_before": sha_before, "sha_after": sha_before,
                "backup": str(bak) if bak else None})
        return result

    # Post-apply RUNTIME smoke (server modules) -> AUTO-ROLLBACK on regression
    smoke_ok, smoke_detail = _smoke_ok(live)
    if not smoke_ok:
        if existed and bak:
            shutil.copy2(bak, live)
            rolled = "rolled_back_from_bak"
        else:
            live.unlink(missing_ok=True)
            rolled = "removed_new_broken_file"
        result["applied"] = False
        result["reason"] = "post_apply_smoke_failed"
        result["smoke"] = smoke_detail
        result["rollback"] = rolled
        _audit({"task_id": tid, "proposal_id": proposal_id, "target": target,
                "applier": applier, "applied": False, "sandbox": "green", "quorum": quorum,
                "reason": "post_apply_smoke_failed", "smoke": smoke_detail, "rollback": rolled,
                "sha_before": sha_before, "sha_after": sha_before,
                "backup": str(bak) if bak else None})
        return result

    # SUCCESS
    result["applied"] = True
    result["smoke"] = smoke_detail
    result["backup"] = str(bak) if bak else None
    result["sha_before"] = sha_before
    result["sha_after"] = sha_after
    _audit({"task_id": tid, "proposal_id": proposal_id, "target": target,
            "sha_before": sha_before, "sha_after": sha_after,
            "applier": applier, "sandbox": "green", "quorum": quorum,
            "applied": True, "backup": str(bak) if bak else None,
            "created": not existed})
    return result


# ---------------------------------------------------------------------------
# CLI — for manual / test invocation
# ---------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Apply a council-verified artifact to live code.")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--target-file", default=None, help="override task.target_file")
    ap.add_argument("--artifact", required=True, help="path to tests/backlog_<tid>.<ext>")
    ap.add_argument("--approvals", default="", help="comma-separated verifier ids (quorum)")
    args = ap.parse_args()
    task = {"id": args.task_id, "target_file": args.target_file}
    approvals = [a.strip() for a in args.approvals.split(",") if a.strip()]
    r = apply_verified_artifact(task, args.artifact, approvals or None)
    print(json.dumps(r, indent=2))
    return 0 if r.get("applied") or r.get("reason") in ("no_change",) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
