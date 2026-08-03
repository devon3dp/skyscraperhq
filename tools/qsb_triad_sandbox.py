#!/usr/bin/env python3
"""qsb_triad_sandbox.py — TRIAD proposal sandbox (three independent checks, 2-of-3 quorum).

Ross 2026-06-13: "code must be run first in sandbox etc and must pass and be
signed off before you install."

WHY THIS EXISTS
    The legacy tools/qsb_proposal_sandbox.py is a SINGLE shallow check: it copies
    the changed file to a tempdir and runs `py_compile` / `node --check` only.
    That is SYNTAX ONLY. It passes files that import-crash, that fail to start a
    server, or that silently break a behaviour the task asked for. A duplicated
    block / IndentationError in a live-service module (the tour-guide failure
    class) or a module that compiles but 404s on `/` slipped straight through to
    the gated deploy. R01 honest: syntax != working.

THE TRIAD (three independent sandboxes, majority verdict)
    Sandbox A — ISOLATION / BUILD
        fresh temp copy of the changed file, then:
          · py_compile                (parse)
          · IMPORT the changed module (catches import-time errors py_compile
                                       misses — top-level NameError, bad import,
                                       side-effecting module body)
          · run adjacent tests        (tests/test_<mod>.py or tools/test_<mod>.py)
          · trivial smoke             (`--help` if argparse, else import-only)
        GREEN iff all attempted checks pass.

    Sandbox B — DIVERSITY REVIEW
        send the unified DIFF to a DIFFERENT model (non-Claude: deepseek/openai)
        through the sanctioned tools/qsb_consult_external.py with a strict rubric
        ("does this introduce a bug / break an interface / fail the task?
        GREEN/RED + one-line reason"). An independent second opinion, not the
        author. Budget caps are enforced by consult_external itself; if the
        provider path is unavailable / over-budget / disabled, Sandbox B votes
        ABSTAIN (never GREEN).

    Sandbox C — INTEGRATION / SMOKE
        run the CANDIDATE file in a FRESH isolated subprocess runtime:
          · server module → launch on a scratch port, prove it binds and an
                            HTTP GET on `/` returns a response (any status).
          · library       → import clean in an isolated subprocess AND prove the
                            immediate neighbours that import it still import.
        GREEN iff it runs without crashing.

VERDICT LOGIC
    · SAFETY paths are HARD-REFUSED before any sandbox runs (is_safety_flagged).
    · overall GREEN needs >= 2 of 3 GREEN.
    · overall GREEN needs UNANIMOUS 3/3 when the change touches a LIVE SERVICE
      file (a *dash*.py / *_server.py / a file with an active systemd unit /
      an http.server module). ABSTAIN is not GREEN, so a live-service change
      cannot pass while the diversity reviewer is unavailable — conservative
      by design.

VERIFY ONLY. The triad judges. It NEVER writes the live tree, NEVER flips a
gate, NEVER auto-deploys. The downstream 2-CEO quorum + Ross/bench gate are
untouched; the triad is an ADDITIONAL hardening layer in front of them.
"""
from __future__ import annotations
import json, sys, os, re, shutil, socket, subprocess, tempfile, difflib, argparse
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# Reuse the legacy sandbox's proposal loading + safety gate (single source of truth).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_proposal_sandbox as SB   # load_proposal, is_safety_flagged, utcnow, ROOT

ROOT = SB.ROOT
RESULTS = ROOT / "data/registries/qsb_triad_sandbox_results.jsonl"
CONSULT = ROOT / "tools/qsb_consult_external.py"

# Live-service filename heuristics (matched on the target relpath / basename).
LIVE_SERVICE_NAME_RE = re.compile(r"(dash.*\.py$|_server\.py$)")
# Server-shaped source markers (mirrors qsb_apply_bridge._smoke_ok).
SERVER_SRC_RE = re.compile(
    r"HTTPServer|create_server|serve_forever|--port|BaseHTTPRequestHandler|app\.run\(")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────────────────────
# proposal → candidate materialisation
# ─────────────────────────────────────────────────────────────────────────────
def _targets(p: dict) -> list[str]:
    return [t for t in (p.get("target_files") or
            ([p.get("target_file")] if p.get("target_file") else [])) if t]


def _candidate_map(p: dict) -> dict[str, str]:
    """{relpath: new_content}. Prefer file_replacements; else fall back to the
    live file (nothing to change → verify the original)."""
    fr = p.get("file_replacements") or {}
    if fr:
        return dict(fr)
    out = {}
    for t in _targets(p):
        lp = ROOT / t
        if lp.exists():
            out[t] = lp.read_text(encoding="utf-8", errors="replace")
    return out


def _unified_diff(relpath: str, new_content: str) -> str:
    live = ROOT / relpath
    before = live.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) \
        if live.exists() else []
    after = new_content.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        before, after, fromfile=f"a/{relpath}", tofile=f"b/{relpath}"))


def _is_live_service(relpath: str, content: str) -> tuple[bool, str]:
    base = Path(relpath).name
    if LIVE_SERVICE_NAME_RE.search(base):
        return True, f"name matches live-service pattern ({base})"
    if SERVER_SRC_RE.search(content or ""):
        return True, "source contains an http-server / server-run marker"
    # active systemd unit whose ExecStart references this file?
    try:
        r = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain"],
            capture_output=True, text=True, timeout=8)
        for line in r.stdout.splitlines():
            unit = line.split()[0] if line.split() else ""
            if not unit.endswith(".service"):
                continue
            cat = subprocess.run(["systemctl", "cat", unit],
                                 capture_output=True, text=True, timeout=5)
            if base in cat.stdout and "active" in line:
                return True, f"active systemd unit {unit} references {base}"
    except Exception:
        pass
    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox A — isolation / build
# ─────────────────────────────────────────────────────────────────────────────
def sandbox_a(cands: dict[str, str], workdir: Path) -> dict:
    checks, ok = [], True

    for relpath, content in cands.items():
        suffix = Path(relpath).suffix
        cpath = workdir / Path(relpath).name
        cpath.write_text(content, encoding="utf-8")

        if suffix == ".py":
            # 1) parse
            r = subprocess.run(["python3", "-m", "py_compile", str(cpath)],
                               capture_output=True, text=True, timeout=30)
            passed = r.returncode == 0
            checks.append({"file": relpath, "check": "py_compile", "ok": passed,
                           "detail": r.stderr[-300:]})
            ok &= passed
            if not passed:
                continue

            # 2) IMPORT the changed module (real neighbours resolve via real dir).
            real_parent = str((ROOT / relpath).resolve().parent)
            imp = subprocess.run(
                ["python3", "-c",
                 "import importlib.util,sys;"
                 f"sys.path.insert(0, {real_parent!r});"
                 f"s=importlib.util.spec_from_file_location('cand_mod', {str(cpath)!r});"
                 "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                 "print('IMPORT_OK')"],
                capture_output=True, text=True, timeout=45)
            passed = imp.returncode == 0 and "IMPORT_OK" in imp.stdout
            checks.append({"file": relpath, "check": "import", "ok": passed,
                           "detail": (imp.stderr or imp.stdout)[-400:]})
            ok &= passed
            if not passed:
                continue

            # 3) adjacent tests (tests/test_<mod>.py, tools/test_<mod>.py)
            stem = Path(relpath).stem
            for cand_test in (ROOT / "tests" / f"test_{stem}.py",
                              ROOT / "tools" / f"test_{stem}.py"):
                if cand_test.exists():
                    tr = subprocess.run(["python3", str(cand_test)],
                                        capture_output=True, text=True, timeout=60,
                                        cwd=str(ROOT))
                    passed = tr.returncode == 0
                    checks.append({"file": relpath, "check": f"adjacent_test:{cand_test.name}",
                                   "ok": passed, "detail": (tr.stderr or tr.stdout)[-300:]})
                    ok &= passed

            # 4) trivial smoke — --help if argparse, else import already proved load
            if "argparse" in content or "ArgumentParser" in content:
                hr = subprocess.run(["python3", str(cpath), "--help"],
                                    capture_output=True, text=True, timeout=20,
                                    env={**os.environ, "PYTHONPATH": real_parent})
                # argparse --help exits 0; a hard crash (traceback) is the failure signal
                passed = "Traceback (most recent call last)" not in hr.stderr
                checks.append({"file": relpath, "check": "smoke:--help", "ok": passed,
                               "detail": (hr.stderr or hr.stdout)[-300:]})
                ok &= passed

        elif suffix == ".json":
            try:
                json.loads(content)
                checks.append({"file": relpath, "check": "json_parse", "ok": True, "detail": ""})
            except Exception as e:
                checks.append({"file": relpath, "check": "json_parse", "ok": False,
                               "detail": str(e)[:300]})
                ok = False
        elif suffix == ".js":
            r = subprocess.run(["node", "--check", str(cpath)],
                               capture_output=True, text=True, timeout=20)
            passed = r.returncode == 0
            checks.append({"file": relpath, "check": "node_check", "ok": passed,
                           "detail": r.stderr[-300:]})
            ok &= passed
        else:
            checks.append({"file": relpath, "check": "utf8_read", "ok": True, "detail": ""})

    return {"sandbox": "A", "role": "isolation/build",
            "verdict": "GREEN" if ok else "RED",
            "reason": "all build checks passed" if ok
                      else "; ".join(f"{c['check']} FAIL" for c in checks if not c["ok"])[:300],
            "checks": checks}


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox B — diversity review (independent non-Claude model)
# ─────────────────────────────────────────────────────────────────────────────
def sandbox_b(p: dict, cands: dict[str, str], provider: str = "deepseek",
              model: str = "deepseek-chat") -> dict:
    diff = "\n".join(_unified_diff(rp, c) for rp, c in cands.items())[:6000]
    if not diff.strip():
        return {"sandbox": "B", "role": "diversity_review", "verdict": "ABSTAIN",
                "reason": "empty diff — nothing to review", "provider": provider}

    task_desc = (p.get("worklist_item") or p.get("reason")
                 or p.get("concrete_change") or p.get("origin") or "(no task text supplied)")
    rubric = textwrap.dedent(f"""\
        You are an independent code reviewer (NOT the author). Judge this unified diff.
        TASK THE CHANGE CLAIMS TO DO: {task_desc}

        Answer in EXACTLY this form on the first line:
          VERDICT: GREEN   (safe, does what the task says, no obvious bug/interface break)
        or
          VERDICT: RED     (introduces a bug, breaks an interface, or fails the task)
        Then one short line: REASON: <one sentence>.

        DIFF:
        {diff}
        """)

    if not CONSULT.exists():
        return {"sandbox": "B", "role": "diversity_review", "verdict": "ABSTAIN",
                "reason": "consult_external tool missing — provider path unavailable",
                "provider": provider}
    try:
        r = subprocess.run(
            ["python3", str(CONSULT), "--provider", provider, "--model", model,
             "--prompt", rubric, "--max-tokens", "120",
             "--reason", "triad_sandbox_diversity_review"],
            capture_output=True, text=True, timeout=90)
    except Exception as e:
        return {"sandbox": "B", "role": "diversity_review", "verdict": "ABSTAIN",
                "reason": f"provider call raised: {e}", "provider": provider}

    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 or "REFUSE" in out or "budget" in out.lower() and "exceed" in out.lower():
        return {"sandbox": "B", "role": "diversity_review", "verdict": "ABSTAIN",
                "reason": f"provider unavailable/over-budget/disabled (rc={r.returncode}): "
                          f"{out.strip()[-200:]}", "provider": provider}

    m = re.search(r"VERDICT:\s*(GREEN|RED)", out, re.IGNORECASE)
    if not m:
        return {"sandbox": "B", "role": "diversity_review", "verdict": "ABSTAIN",
                "reason": f"no parseable verdict in provider reply: {out.strip()[-200:]}",
                "provider": provider}
    verdict = m.group(1).upper()
    rm = re.search(r"REASON:\s*(.+)", out)
    reason = (rm.group(1).strip() if rm else "model reviewed the diff")[:240]
    return {"sandbox": "B", "role": "diversity_review", "verdict": verdict,
            "reason": reason, "provider": provider, "model": model}


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox C — integration / smoke (fresh isolated runtime)
# ─────────────────────────────────────────────────────────────────────────────
def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def sandbox_c(cands: dict[str, str], workdir: Path) -> dict:
    checks, ok = [], True

    for relpath, content in cands.items():
        if Path(relpath).suffix != ".py":
            checks.append({"file": relpath, "check": "skip_non_py", "ok": True, "detail": ""})
            continue

        cpath = workdir / f"cand_{Path(relpath).name}"
        cpath.write_text(content, encoding="utf-8")
        real_parent = str((ROOT / relpath).resolve().parent)
        env = {**os.environ, "PYTHONPATH": real_parent}

        is_server = bool(SERVER_SRC_RE.search(content))

        if is_server and "--port" in content:
            # launch on a scratch port; prove it binds + answers HTTP
            port = _free_port()
            proc = None
            try:
                proc = subprocess.Popen(
                    ["python3", str(cpath), "--port", str(port)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                bound, http_ok, detail = _probe_http(proc, port)
                passed = bound and http_ok
                checks.append({"file": relpath, "check": "server_boot+http",
                               "ok": passed, "detail": detail})
                ok &= passed
            finally:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
        elif is_server:
            # server-shaped but no --port flag: prove it at least imports without crash
            passed, detail = _subproc_import(cpath, env)
            checks.append({"file": relpath, "check": "server_import_only",
                           "ok": passed, "detail": detail})
            ok &= passed
        else:
            # library: import clean in isolated subprocess
            passed, detail = _subproc_import(cpath, env)
            checks.append({"file": relpath, "check": "lib_import", "ok": passed, "detail": detail})
            ok &= passed
            # neighbour check: modules in the real dir that import this one still import
            n_ok, n_detail = _neighbour_import_ok(relpath, workdir, content)
            checks.append({"file": relpath, "check": "neighbour_import",
                           "ok": n_ok, "detail": n_detail})
            ok &= n_ok

    return {"sandbox": "C", "role": "integration/smoke",
            "verdict": "GREEN" if ok else "RED",
            "reason": "runs without crashing" if ok
                      else "; ".join(f"{c['check']} FAIL" for c in checks if not c["ok"])[:300],
            "checks": checks}


def _probe_http(proc: subprocess.Popen, port: int) -> tuple[bool, bool, str]:
    import time, urllib.request, urllib.error
    deadline = time.time() + 8
    while time.time() < deadline:
        if proc.poll() is not None:
            err = (proc.stderr.read() if proc.stderr else "")[-400:]
            return False, False, f"process exited early rc={proc.returncode}: {err}"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                return True, True, f"HTTP {resp.status} on /"
        except urllib.error.HTTPError as e:
            return True, True, f"HTTP {e.code} on / (bound + serving)"
        except Exception:
            time.sleep(0.4)
    return False, False, "did not bind / serve within 8s"


def _subproc_import(cpath: Path, env: dict) -> tuple[bool, str]:
    r = subprocess.run(
        ["python3", "-c",
         "import importlib.util,sys;"
         f"s=importlib.util.spec_from_file_location('cand_int', {str(cpath)!r});"
         "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print('OK')"],
        capture_output=True, text=True, timeout=45, env=env)
    return (r.returncode == 0 and "OK" in r.stdout), (r.stderr or r.stdout)[-400:]


def _neighbour_import_ok(relpath: str, workdir: Path, content: str) -> tuple[bool, str]:
    """Immediate neighbours that import this module must still import with the
    CANDIDATE shadowing the real file. Best-effort, capped at 5 neighbours."""
    mod = Path(relpath).stem
    real_dir = (ROOT / relpath).resolve().parent
    # shadow: candidate written under the module's real name inside workdir
    shadow = workdir / f"{mod}.py"
    shadow.write_text(content, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": f"{workdir}:{real_dir}"}
    tested, broken = 0, []
    for f in sorted(real_dir.glob("*.py")):
        if f.name == Path(relpath).name or f.name.startswith("test_"):
            continue
        try:
            txt = f.read_text(errors="ignore")
        except Exception:
            continue
        if re.search(rf"\bimport\s+{re.escape(mod)}\b", txt):
            r = subprocess.run(["python3", "-c", f"import {f.stem}"],
                               capture_output=True, text=True, timeout=30, env=env)
            tested += 1
            if r.returncode != 0 and mod in (r.stderr or ""):
                broken.append(f"{f.name}: {(r.stderr or '')[-160:]}")
            if tested >= 5:
                break
    if broken:
        return False, "neighbours broke: " + " | ".join(broken)
    return True, (f"{tested} neighbour(s) still import cleanly" if tested
                  else "no neighbours import this module")


# ─────────────────────────────────────────────────────────────────────────────
# verdict logic
# ─────────────────────────────────────────────────────────────────────────────
def _decide(sub: list[dict], live_service: bool) -> tuple[str, str]:
    greens = sum(1 for s in sub if s["verdict"] == "GREEN")
    required = 3 if live_service else 2
    tag = "3/3 (live-service)" if live_service else "2/3"
    if greens >= required:
        return "green", f"{greens}/3 GREEN meets {tag} quorum"
    return "red", (f"{greens}/3 GREEN < required {tag} "
                   f"[{', '.join(s['sandbox'] + '=' + s['verdict'] for s in sub)}]")


def write_result(rec: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def run_triad(pid: str, skip_provider: bool = False) -> dict:
    """Run all three sandboxes and return the quorum verdict. VERIFY ONLY."""
    p = SB.load_proposal(pid)
    if not p:
        rec = {"ts": utcnow(), "id": pid, "verdict": "not_found", "ok": False,
               "engine": "triad"}
        write_result(rec)
        return rec

    # HARD safety refusal — before any sandbox runs.
    flagged, why = SB.is_safety_flagged(p)
    if flagged:
        rec = {"ts": utcnow(), "id": pid, "verdict": "safety_refused",
               "reason": why, "ok": False, "engine": "triad"}
        write_result(rec)
        return rec

    cands = _candidate_map(p)
    if not cands:
        rec = {"ts": utcnow(), "id": pid, "verdict": "red", "engine": "triad",
               "reason": "no candidate content (no file_replacements, no live target)",
               "ok": False}
        write_result(rec)
        return rec

    # live-service classification (any target)
    live_service, ls_reason = False, ""
    for rp, content in cands.items():
        f, r = _is_live_service(rp, content)
        if f:
            live_service, ls_reason = True, r
            break

    work = Path(tempfile.mkdtemp(prefix="qsb_triad_"))
    (work / "A").mkdir(exist_ok=True)
    (work / "C").mkdir(exist_ok=True)
    try:
        a = sandbox_a(cands, work / "A")
        c = sandbox_c(cands, work / "C")
        if skip_provider:
            b = {"sandbox": "B", "role": "diversity_review", "verdict": "ABSTAIN",
                 "reason": "provider review skipped (--skip-provider)", "provider": "none"}
        else:
            b = sandbox_b(p, cands)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    sub = [a, b, c]
    verdict, reason = _decide(sub, live_service)
    rec = {
        "ts": utcnow(), "id": pid, "engine": "triad", "verdict": verdict,
        "ok": verdict == "green",
        "live_service": live_service, "live_service_reason": ls_reason,
        "quorum_rule": "3/3 (live-service)" if live_service else "2/3",
        "quorum_reason": reason,
        "targets": _targets(p),
        "sandboxes": [
            {"sandbox": s["sandbox"], "role": s["role"],
             "verdict": s["verdict"], "reason": s["reason"],
             **({"checks": s["checks"]} if "checks" in s else {}),
             **({"provider": s["provider"]} if "provider" in s else {})}
            for s in sub
        ],
        "verify_only": True,
    }
    write_result(rec)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("proposal_id")
    ap.add_argument("--skip-provider", action="store_true",
                    help="skip Sandbox B provider call (it votes ABSTAIN)")
    args = ap.parse_args()
    rec = run_triad(args.proposal_id, skip_provider=args.skip_provider)
    print(json.dumps(rec, indent=2))
    return 0 if rec.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
