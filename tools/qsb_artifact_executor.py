#!/usr/bin/env python3
"""
qsb_artifact_executor.py — OBJECTIVE execution of a code artifact (BUILD PIECE 2 of 3, 2026-07-29).

The council's verify path used to have two LLMs *read* the artifact text and judge whether it
"looks" done. That let a real bug (e.g. a test file missing `import os`) sail through as "green",
while good code got rejected on vibes. This module makes verification EXECUTE the code instead.

Given an artifact that is Python code (a single source string) OR a file_replacements map
{path: content}, it:
  1. writes every file into an ISOLATED per-call scratch dir under a system temp location
     (NEVER the live repo tree),
  2. runs `python3 -m py_compile` on each .py file (real compile — catches SyntaxError),
  3. if any file is/contains a test (name looks like a test, or has __main__ / asserts / a
     test_ function), RUNS it with `python3 <file>` and captures real pass/fail + stderr,
  4. returns a structured verdict:
        {executed, language, compile_ok, run_ok, ran_a_test, output, error, files:[...]}

Honesty rules:
  - execution is ground truth. compile_ok / run_ok are objective facts about the bytes.
  - for NON-Python or NON-executable artifacts (html, css, json, prose, a bare function with no
    test / no runnable entrypoint) it sets executed=False and says why — the caller then falls
    back to LLM judgment for "does it satisfy the intent".
  - it NEVER imports or runs anything from the live tree; the scratch dir is isolated and removed.
  - time-bounded (compile + run each under a hard timeout) so a hung/infinite artifact can't wedge
    the council.

No gates flipped, no network, no live-tree writes, no CLAUDE.md/vault/.env/gate/oanda touches.
"""
import os
import re
import sys
import shutil
import tempfile
import subprocess

# ---- hard bounds --------------------------------------------------------------
COMPILE_TIMEOUT_S = 20          # per py_compile invocation
RUN_TIMEOUT_S = 30              # per test run
OUTPUT_CAP = 8000               # cap captured output so a chatty test can't flood the journal

# never let an artifact reach outside its scratch dir when we write its files
_SAFE_REL = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./\-]*$")


def _looks_python(text: str) -> bool:
    """Heuristic: does this text read as Python source? Deliberately conservative — if we can't be
    fairly sure it's Python we say no and let the LLM path judge it."""
    if not text or not text.strip():
        return False
    low = text.lower()
    # obvious NON-python artifacts
    if "<!doctype" in low or "<html" in low or "<svg" in low:
        return False
    t = text.strip()
    if t[:1] in "{[" and t[-1:] in "}]":
        # likely JSON (a bare dict/list) — not something we py_compile as a script
        # (a python file rarely starts at col 0 with a bare { )
        return False
    py_signals = 0
    for pat in (r"^\s*def\s+\w+\s*\(", r"^\s*class\s+\w+", r"^\s*import\s+\w",
                r"^\s*from\s+\w[\w.]*\s+import\b", r"^\s*if\s+__name__\s*==",
                r"^\s*assert\b", r"^\s*print\s*\("):
        if re.search(pat, text, re.MULTILINE):
            py_signals += 1
    return py_signals >= 1


def _is_test_file(name: str, text: str) -> bool:
    """Is this file a genuine TEST worth RUNNING? 2026-07-29 fix: only run real tests, never
    feature/server modules. A bare `if __name__==__main__` or `assert` is NOT enough — a server
    module (e.g. qsb_tour_guide_server.py) has `__main__: create_server(port)` which starts an
    HTTP server that can't bind in the sandbox, giving a FALSE run failure. Feature modules are
    py_compile-only (objective-partial); genuine tests still run and catch real runtime bugs."""
    norm = name.replace("\\", "/").lower()
    base = os.path.basename(norm)
    if base.startswith("test_") or base.endswith("_test.py") or base == "test.py":
        return True
    if norm.startswith("tests/") or "/tests/" in norm:
        return True
    if re.search(r"^\s*def\s+test_\w+", text, re.MULTILINE):
        return True
    # a __main__ block counts ONLY if it looks like a self-checking test harness (asserts/checks
    # + an exit code) AND does NOT start a server / bind a socket / enter an event loop.
    has_main = re.search(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]", text, re.MULTILINE)
    looks_testy = re.search(r"\b(assert|check\()", text) and re.search(r"sys\.exit\(", text)
    starts_service = re.search(r"(create_server|serve_forever|\.run\(|HTTPServer|socket\(|app\.run|"
                               r"uvicorn|Flask\(|while\s+True)", text)
    if has_main and looks_testy and not starts_service:
        return True
    return False


def _write_scratch(file_map: dict, scratch: str) -> list:
    """Write each {relpath: content} into the scratch dir safely. Returns list of abs paths."""
    written = []
    for rel, content in file_map.items():
        rel = (rel or "").strip().lstrip("/")
        if not rel or not _SAFE_REL.match(rel) or ".." in rel.split("/"):
            # ignore unsafe / traversal paths — never write outside scratch
            rel = "artifact_%d.py" % (len(written) + 1)
        dst = os.path.join(scratch, rel)
        os.makedirs(os.path.dirname(dst) or scratch, exist_ok=True)
        with open(dst, "w") as f:
            f.write(content if isinstance(content, str) else str(content))
        written.append(dst)
    return written


def _py_compile(path: str) -> tuple:
    """(ok, err_text). Real compile via a subprocess so a SyntaxError can't crash us."""
    try:
        r = subprocess.run([sys.executable, "-m", "py_compile", path],
                           capture_output=True, text=True, timeout=COMPILE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return (False, "py_compile timed out after %ss" % COMPILE_TIMEOUT_S)
    except Exception as e:
        return (False, "py_compile error: %s" % e)
    if r.returncode == 0:
        return (True, "")
    return (False, ((r.stderr or "") + (r.stdout or "")).strip()[:OUTPUT_CAP])


def _run(path: str, scratch: str) -> tuple:
    """(ok, output). Runs `python3 <path>` inside the scratch cwd, isolated from the live tree.
    Ground truth: exit 0 == pass. Captures stdout+stderr (so a NameError at RUNTIME is caught —
    py_compile does NOT catch undefined-name-at-runtime; only execution does)."""
    env = dict(os.environ)
    # isolate imports to the scratch dir only — do NOT let it import the live repo
    env["PYTHONPATH"] = scratch
    env.pop("PYTHONSTARTUP", None)
    try:
        r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           timeout=RUN_TIMEOUT_S, cwd=scratch, env=env)
    except subprocess.TimeoutExpired:
        return (False, "RUN TIMED OUT after %ss (possible infinite loop)" % RUN_TIMEOUT_S)
    except Exception as e:
        return (False, "run error: %s" % e)
    out = ((r.stdout or "") + (("\n--- stderr ---\n" + r.stderr) if r.stderr else "")).strip()
    return (r.returncode == 0, out[:OUTPUT_CAP])


def execute_artifact(artifact=None, file_replacements=None, artifact_name="artifact.py") -> dict:
    """Execute a code artifact in an isolated scratch dir.

    artifact:            a raw code string (single-file deliverable), OR
    file_replacements:   {relpath: content} map (multi-file deliverable).
    artifact_name:       filename to use when `artifact` is a bare string.

    Returns:
      {executed: bool,          # did we actually compile/run anything objective?
       language: str,           # 'python' | 'non-python'
       compile_ok: bool|None,   # None when not applicable
       run_ok: bool|None,       # None when nothing runnable
       ran_a_test: bool,
       output: str,             # real captured error/pass output
       error: str,              # the true failure reason when compile/run failed
       files: [names]}
    """
    # normalize to a file map
    file_map = {}
    if file_replacements and isinstance(file_replacements, dict):
        file_map = {k: v for k, v in file_replacements.items() if isinstance(v, str)}
    elif isinstance(artifact, str):
        file_map = {artifact_name: artifact}
    else:
        return {"executed": False, "language": "unknown", "compile_ok": None, "run_ok": None,
                "ran_a_test": False, "output": "", "error": "no artifact/file_replacements given",
                "files": []}

    if not file_map:
        return {"executed": False, "language": "unknown", "compile_ok": None, "run_ok": None,
                "ran_a_test": False, "output": "", "error": "empty artifact", "files": []}

    # decide which files are python we can compile.
    # For a bare code STRING (not an explicit file map) the caller-supplied name may be a generic
    # default (artifact.py), so we judge python-ness by CONTENT — an html/json/prose blob handed in
    # as a string must NOT be treated as broken Python; it is non-executable -> LLM intent path.
    bare_string = (file_replacements is None and isinstance(artifact, str))
    if bare_string:
        only = list(file_map)[0]
        if _looks_python(file_map[only]):
            file_map = {"artifact.py": file_map[only]}
            py_files = {"artifact.py": file_map["artifact.py"]}
        else:
            py_files = {}
    else:
        # explicit file map: trust a .py extension, else sniff content
        py_files = {n: c for n, c in file_map.items()
                    if n.endswith(".py") or _looks_python(c)}

    if not py_files:
        return {"executed": False, "language": "non-python", "compile_ok": None, "run_ok": None,
                "ran_a_test": False, "output": "",
                "error": "artifact is not executable Python (html/css/json/prose) — "
                         "falls back to LLM judgment for intent",
                "files": list(file_map)}

    scratch = tempfile.mkdtemp(prefix="qsb_artifact_exec_")
    try:
        _write_scratch(file_map, scratch)

        # 1) COMPILE every python file
        compile_ok = True
        compile_err = ""
        for name in py_files:
            abspath = os.path.join(scratch, name)
            ok, err = _py_compile(abspath)
            if not ok:
                compile_ok = False
                compile_err = "%s: %s" % (name, err)
                break
        if not compile_ok:
            return {"executed": True, "language": "python", "compile_ok": False, "run_ok": None,
                    "ran_a_test": False, "output": compile_err, "error": compile_err,
                    "files": list(file_map)}

        # 2) find a runnable test / entrypoint and RUN it (catches runtime NameError etc.)
        test_files = [n for n, c in py_files.items() if _is_test_file(n, c)]
        if not test_files:
            # compiles, but nothing to execute for a real pass/fail signal.
            return {"executed": True, "language": "python", "compile_ok": True, "run_ok": None,
                    "ran_a_test": False, "output": "compiled clean; no runnable test/entrypoint present",
                    "error": "", "files": list(file_map)}

        run_ok = True
        run_output = []
        run_error = ""
        for name in test_files:
            abspath = os.path.join(scratch, name)
            ok, out = _run(abspath, scratch)
            run_output.append("[%s] %s\n%s" % (name, "PASS" if ok else "FAIL", out))
            if not ok:
                run_ok = False
                run_error = "%s failed:\n%s" % (name, out)
                break
        return {"executed": True, "language": "python", "compile_ok": True, "run_ok": run_ok,
                "ran_a_test": True, "output": "\n".join(run_output)[:OUTPUT_CAP],
                "error": run_error, "files": list(file_map)}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    # PROOF: good code that runs clean, and the exact broken artifact from tonight.
    print("=== (1) GOOD: a working function + its passing test ===")
    good = (
        "import os\n"
        "def add(a, b):\n"
        "    return a + b\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "    assert os.path.basename('/x/y.py') == 'y.py'\n"
        "if __name__ == '__main__':\n"
        "    test_add()\n"
        "    print('OK add()')\n"
    )
    g = execute_artifact(artifact=good, artifact_name="test_add.py")
    print("  executed=%s compile_ok=%s run_ok=%s ran_a_test=%s" %
          (g["executed"], g["compile_ok"], g["run_ok"], g["ran_a_test"]))
    print("  output:", g["output"].replace("\n", " | ")[:160])

    print("\n=== (2) BROKEN (tonight's bug): a test file that USES os but never imports it ===")
    broken = (
        "def add(a, b):\n"
        "    return a + b\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "    # uses os without importing it -> NameError at RUNTIME (py_compile does NOT catch this)\n"
        "    assert os.path.basename('/x/y.py') == 'y.py'\n"
        "if __name__ == '__main__':\n"
        "    test_add()\n"
        "    print('OK add()')\n"
    )
    b = execute_artifact(artifact=broken, artifact_name="test_add.py")
    print("  executed=%s compile_ok=%s run_ok=%s ran_a_test=%s" %
          (b["executed"], b["compile_ok"], b["run_ok"], b["ran_a_test"]))
    print("  error:", (b["error"] or b["output"]).replace("\n", " | ")[:200])
