#!/usr/bin/env python3
"""qsb_ceo_proposer.py — turn TP-Pip, Asa (acer_cass) and Wren from liveness-only
workers into workers that PROPOSE real, sandbox-testable improvements through the
HONEST pipeline (propose -> sandbox -> multi-sig -> apply).

2026-07-29, Ross goal: "make them generate genuine, sandbox-testable improvement
proposals" — not just answer questions to draw map trains.

What each cycle does
--------------------
1. Pull ONE real, small improvement opportunity from the worklist. Source order:
      (a) data/registries/qsb_self_audit_findings.jsonl (if present)
      (b) docs/CODEX_WORKLIST.md  (parsed TIER items — each is a genuine,
          sandbox-verifiable, self-contained job authored by the audit sweep)
   Only opportunities that a text-only cockpit can fully author are used:
   "write a NEW self-contained standalone test file for <existing source>".
   Those items give a single, new, whole-file target the CEO can emit in full.

2. Ask a REAL CEO cockpit to DRAFT the whole new file:
      TP  @ http://<ip>:9120/api/chat   field "prompt"  -> key "reply"
      Asa @ http://<ip>:9120/api/chat   field "prompt"  -> key "reply"
      Wren @ http://127.0.0.1:8851/api/wren_chat field "text" -> key "reply"
   (cockpit addresses read LIVE from presence.json; fall back to last-known IPs).

3. NORMALIZE the CEO's answer into the file_replacements shape the sandbox runs
   ({relpath: FULL new file content}) — the exact schema
   tools/qsb_proposal_sandbox.py + tools/qsb_provider_agent.py accept — and QUEUE
   it to data/registries/qsb_proposal_queue.jsonl with status "queued_unsigned".
   NEVER auto-apply. NEVER auto-sign. Multi-sig + Ross gate stay intact.

Honesty (R01) — a proposal is queued ONLY when ALL of these hold:
   - the cockpit was reachable and gave a real reply (not an error sentinel),
   - the reply, once fenced-code is stripped, is a PLAUSIBLE whole Python file
     (not a unified diff, not an apology, not a one-liner),
   - it passes `python3 -m py_compile` locally (so the sandbox will reach a real
     green/red verdict, not choke on garbage),
   - the target path is NEW (we never silently overwrite an existing file) and is
     NOT a SAFETY_DENY path (CLAUDE.md / vault / .env / oanda / gate files).
   Otherwise: log "needs refinement" and queue NOTHING (no fake proposal).

systemd: qsb-ceo-proposer.timer (~5 min). Run once: python3 tools/qsb_ceo_proposer.py
Options:
   --ceo tp|asa|wren   force a specific CEO (default: rotate by clock)
   --dry-run           draft + validate but DO NOT write to the queue
"""
from __future__ import annotations
import argparse, ast, json, re, subprocess, sys, tempfile, time, uuid, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
PRESENCE = REG / "leadership_comms" / "presence.json"
QUEUE = REG / "qsb_proposal_queue.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
SELF_AUDIT = REG / "qsb_self_audit_findings.jsonl"
WORKLIST = ROOT / "docs" / "CODEX_WORKLIST.md"
PROPOSER_LOG = REG / "qsb_ceo_proposer_log.jsonl"

# SAFETY_DENY — proposals may NEVER target these (mirrors the sandbox + checker +
# CLAUDE.md 2026-06-13). We refuse before ever writing to the queue.
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

# CEO -> (presence key, station id on the map, fallback cockpit ip, display, kind)
CEOS = {
    "tp":   ("tp",  "tp_pip",    "192.168.1.91", "TP-Pip", "cockpit"),
    "asa":  ("asa", "acer_cass", "192.168.1.41", "Asa",    "cockpit"),
    "wren": ("wren", "wren",     "127.0.0.1",    "Wren",   "wren"),
}
WREN_MIND = "http://127.0.0.1:8851/api/wren_chat"   # field "text"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── honesty helpers ────────────────────────────────────────────────────

def _bad_reply(reply: str) -> bool:
    """True when a cockpit reply is empty or an error/offline sentinel — never
    build a proposal on one of these (R01)."""
    r = (reply or "").lower().strip()
    if not r:
        return True
    return r.startswith(("(cockpit", "local generation failed", "(couldn't reach",
                         "(error", "error:")) or "unreachable" in r


def _looks_like_unified_diff(text: str) -> bool:
    """Reject diffs/hunks — the sandbox needs WHOLE-FILE content, not a diff
    (same rule as qsb_provider_agent._looks_like_unified_diff)."""
    t = (text or "").lstrip()
    if t.startswith(("--- ", "+++ ", "diff --git", "@@ ", "Index: ")):
        return True
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    diffish = sum(1 for ln in lines if ln[:1] in "+-@")
    return diffish >= max(3, int(0.6 * len(lines)))


def _extract_code(reply: str) -> str:
    """Pull the file body out of a cockpit reply. Prefer a fenced ```python
    block; else strip any leading prose before the first `#!`/`import`/`\"\"\"`."""
    if not reply:
        return ""
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", reply, re.DOTALL)
    if m:
        return m.group(1).strip("\n")
    # No fence: try to find the first code-ish line and take from there.
    lines = reply.splitlines()
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if s.startswith(("#!", "import ", "from ", '"""', "'''", "#")):
            return "\n".join(lines[i:]).strip("\n")
    return reply.strip("\n")


def _py_compiles(code: str) -> tuple[bool, str]:
    """Local pre-check: does this parse + py_compile? (The sandbox will run the
    SAME py_compile — this just stops us queueing garbage that can't reach a
    real verdict.)"""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, f"ast.parse: {e}"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(code)
        path = tf.name
    try:
        r = subprocess.run([sys.executable, "-m", "py_compile", path],
                           capture_output=True, text=True, timeout=20)
        ok = r.returncode == 0
        return ok, ("" if ok else r.stderr.strip()[-300:])
    finally:
        Path(path).unlink(missing_ok=True)
        Path(path + "c").unlink(missing_ok=True)


def _is_safety(relpath: str) -> bool:
    return any(sp in relpath for sp in SAFETY_PATHS)


def _concrete_enough(code: str) -> tuple[bool, str]:
    """A drafted new test file must be a *real* self-contained test: has a main
    guard or asserts, references an OVERALL/exit convention, and is non-trivial.
    Guards against a cockpit returning a stub."""
    if len(code) < 200:
        return False, "too short to be a real test file"
    low = code.lower()
    if "def " not in low and "assert" not in low:
        return False, "no functions/asserts — not a real test"
    if not (re.search(r"\bassert\b", code) or "check(" in low):
        return False, "no assertions — a test with no checks is not concrete"
    return True, ""


# ── opportunity sourcing ────────────────────────────────────────────────

def _worklist_test_items() -> list[dict]:
    """Parse docs/CODEX_WORKLIST.md for items that create a NEW standalone test
    file for an EXISTING source file — the shape a text-only cockpit can fully
    author. Returns [{title, target (new tests/..py), source (existing tool)}]."""
    if not WORKLIST.exists():
        return []
    text = WORKLIST.read_text(errors="ignore")
    items = []
    # Split into "### N. Title" blocks.
    blocks = re.split(r"\n### ", text)
    for b in blocks:
        head = b.splitlines()[0] if b else ""
        # only NEW test-file items — they name `new tests/....py (reads tools/....py)`
        m = re.search(r"new\s+`?(tests/[A-Za-z0-9_./]+\.py)`?\s*\(reads\s+`?(tools/[A-Za-z0-9_./]+\.py)`?", b)
        if not m:
            continue
        target, source = m.group(1), m.group(2)
        if (ROOT / target).exists():        # never overwrite an existing file
            continue
        if not (ROOT / source).exists():     # source to test must be real
            continue
        if _is_safety(target) or _is_safety(source):
            continue
        # grab the "What:" bullet as the brief
        wm = re.search(r"\*\*What:\*\*\s*(.+?)(?:\n- \*\*|\n\n|\Z)", b, re.DOTALL)
        brief = re.sub(r"\s+", " ", (wm.group(1) if wm else head)).strip()[:900]
        items.append({"title": head.strip("# .").strip(),
                      "target": target, "source": source, "brief": brief})
    return items


def _self_audit_items() -> list[dict]:
    """Optional: read qsb_self_audit_findings.jsonl for the same 'new test file'
    shape, if that registry exists. Findings must carry target + source paths."""
    if not SELF_AUDIT.exists():
        return []
    items = []
    for ln in SELF_AUDIT.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        target = d.get("target") or d.get("new_file") or ""
        source = d.get("source") or d.get("reads") or ""
        if not (target.startswith("tests/") and source.startswith("tools/")):
            continue
        if (ROOT / target).exists() or not (ROOT / source).exists():
            continue
        if _is_safety(target) or _is_safety(source):
            continue
        items.append({"title": d.get("title", target),
                      "target": target, "source": source,
                      "brief": (d.get("what") or d.get("brief") or "")[:900]})
    return items


def pick_opportunity(seed: int) -> dict | None:
    """Self-audit findings first, then worklist. Rotate by seed so successive
    cycles pick different real items."""
    pool = _self_audit_items() + _worklist_test_items()
    if not pool:
        return None
    return pool[seed % len(pool)]


# ── cockpit call ────────────────────────────────────────────────────────

def _cockpit_ip(pres_key: str, fallback: str) -> str:
    try:
        p = json.loads(PRESENCE.read_text())
        return (p.get(pres_key, {}) or {}).get("reachable_addr") or fallback
    except Exception:
        return fallback


def ask_ceo(ceo: str, prompt: str, timeout: int = 130) -> str:
    pres_key, station, fallback, disp, kind = CEOS[ceo]
    if kind == "wren":
        url, payload = WREN_MIND, {"text": prompt}
    else:
        ip = _cockpit_ip(pres_key, fallback)
        url, payload = f"http://{ip}:9120/api/chat", {"prompt": prompt}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read() or b"{}")
    return (d.get("reply") or d.get("response") or d.get("text") or "").strip()


def build_brief(opp: dict) -> str:
    """The concrete ask handed to the cockpit — includes the real source excerpt
    so the draft is written against actual code, not invented."""
    src = ROOT / opp["source"]
    src_text = src.read_text(errors="ignore")
    excerpt = src_text if len(src_text) <= 6000 else src_text[:6000] + "\n# ...[source truncated]..."
    return f"""You are a QSB Tower engineer. Write ONE complete, self-contained Python \
test file to be saved at `{opp['target']}`. It tests the EXISTING module below.

TASK: {opp['title']}
DETAIL: {opp['brief']}

HARD RULES (the file is auto-run in a sandbox — get these right):
- Output ONLY the file content, inside a single ```python fenced block. No prose.
- Standalone script style used in this repo: NO pytest. Import the target module
  by path with importlib.util.spec_from_file_location, run plain asserts (or a
  small check() helper), print a final "OVERALL: PASS" / "OVERALL: FAIL" line,
  and end with sys.exit(0 on pass / 1 on fail).
- Pure / network-free only. Do NOT call any model, socket, or broker.
- Compute the target module path from __file__ so it works from the repo root:
  ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  then spec_from_file_location on os.path.join(ROOT, "{opp['source']}").
- It MUST be valid Python that `python3 -m py_compile` accepts.

EXISTING SOURCE `{opp['source']}` (test against THIS):
```python
{excerpt}
```
Return the whole test file now, in one ```python block."""


# ── logging ─────────────────────────────────────────────────────────────

def _log(row: dict) -> None:
    row = {"ts": _utc(), **row}
    with PROPOSER_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _stamp_f47(summary: str, extra: dict) -> None:
    rec = {"ts": _utc(), "kind": "ceo_proposal_drafted", "operator": "qsb_ceo_proposer",
           "summary": summary[:500], **extra}
    with F47.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def queue_proposal(opp: dict, ceo: str, code: str) -> str:
    """Write a sandbox-runnable file_replacements proposal. status=queued_unsigned,
    NO sigs, NOT applied — multi-sig + Ross gate untouched."""
    pid = f"ceo_{ceo}_{uuid.uuid4().hex[:10]}"
    relpath = opp["target"]
    row = {
        "ts": _utc(),
        "proposal_id": pid,
        "source": f"ceo_proposer:{ceo}",
        "origin_ceo": CEOS[ceo][3],
        "worklist_item": opp["title"],
        "tests_source": opp["source"],
        "target_files": [relpath],
        "target_file": relpath,
        "patch_body": code[:8000],
        "file_replacements": {relpath: code},
        "status": "queued_unsigned",     # NEVER auto-signed / auto-applied
        "sigs": [],                       # empty — needs 3 unique-class + Ross
    }
    with QUEUE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return pid


# ── one cycle ───────────────────────────────────────────────────────────

def run_cycle(ceo: str | None, dry_run: bool = False) -> dict:
    seed = int(time.time() // 300)
    if ceo is None:
        ceo = ["tp", "asa", "wren"][seed % 3]
    if ceo not in CEOS:
        return {"ok": False, "reason": f"unknown ceo {ceo}"}
    disp = CEOS[ceo][3]

    opp = pick_opportunity(seed)
    if not opp:
        _log({"ceo": ceo, "result": "no_opportunity",
              "note": "no NEW-test-file worklist/self-audit item available"})
        print(f"[proposer] no real opportunity available — NOTHING queued.")
        return {"ok": False, "reason": "no_opportunity"}

    print(f"[proposer] {disp} <- opportunity: {opp['title']} (new {opp['target']})", flush=True)

    # 1. real draft from the real cockpit
    try:
        reply = ask_ceo(ceo, build_brief(opp))
    except Exception as e:
        _log({"ceo": ceo, "opportunity": opp["title"], "result": "unreachable",
              "error": str(e)[:200]})
        print(f"[proposer] {disp} unreachable ({str(e)[:60]}) — NO proposal (honest).")
        return {"ok": False, "reason": "unreachable"}

    if _bad_reply(reply):
        _log({"ceo": ceo, "opportunity": opp["title"], "result": "non_answer",
              "reply_head": (reply or "")[:120]})
        print(f"[proposer] {disp} gave a non-answer — NO proposal (honest).")
        return {"ok": False, "reason": "non_answer"}

    # 2. normalize -> whole-file content
    code = _extract_code(reply)
    if _looks_like_unified_diff(code):
        _log({"ceo": ceo, "opportunity": opp["title"], "result": "needs_refinement",
              "why": "reply is a diff, not whole-file content"})
        print(f"[proposer] {disp} returned a diff, not whole file — needs refinement, NOTHING queued.")
        return {"ok": False, "reason": "diff_not_wholefile"}

    if _is_safety(opp["target"]):
        _log({"ceo": ceo, "opportunity": opp["title"], "result": "safety_refused",
              "target": opp["target"]})
        print(f"[proposer] target {opp['target']} is SAFETY_DENY — refused.")
        return {"ok": False, "reason": "safety"}

    ok, why = _concrete_enough(code)
    if not ok:
        _log({"ceo": ceo, "opportunity": opp["title"], "result": "needs_refinement",
              "why": why, "code_head": code[:200]})
        print(f"[proposer] {disp} draft not concrete ({why}) — needs refinement, NOTHING queued.")
        return {"ok": False, "reason": f"not_concrete:{why}"}

    # 3. local py_compile pre-check so the sandbox reaches a real verdict
    compiles, err = _py_compiles(code)
    if not compiles:
        _log({"ceo": ceo, "opportunity": opp["title"], "result": "needs_refinement",
              "why": "py_compile failed", "err": err, "code_head": code[:200]})
        print(f"[proposer] {disp} draft doesn't compile ({err[:80]}) — needs refinement, NOTHING queued.")
        return {"ok": False, "reason": "compile_fail"}

    if dry_run:
        print(f"[proposer] DRY-RUN: {disp} produced a valid draft for {opp['target']} "
              f"({len(code)} chars) — would queue (not written).")
        return {"ok": True, "dry_run": True, "ceo": ceo, "target": opp["target"],
                "code_len": len(code)}

    # 4. QUEUE only (no sig, no apply)
    pid = queue_proposal(opp, ceo, code)
    _log({"ceo": ceo, "opportunity": opp["title"], "result": "queued",
          "proposal_id": pid, "target": opp["target"], "code_len": len(code)})
    _stamp_f47(f"{disp} drafted a real proposal {pid} -> {opp['target']} "
               f"(new test for {opp['source']}); queued unsigned for sandbox+multi-sig",
               {"proposal_id": pid, "origin_ceo": disp, "target": opp["target"]})
    print(f"[proposer] {disp} -> queued proposal {pid} for {opp['target']} "
          f"({len(code)} chars). NOT signed, NOT applied.")
    return {"ok": True, "ceo": ceo, "proposal_id": pid, "target": opp["target"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceo", choices=list(CEOS.keys()), default=None,
                    help="force a specific CEO (default: rotate by clock)")
    ap.add_argument("--dry-run", action="store_true",
                    help="draft + validate but do not write to the queue")
    a = ap.parse_args()
    out = run_cycle(a.ceo, a.dry_run)
    # Exit non-zero ONLY for genuine infrastructure failures so that
    # systemd's `failed` state stays a meaningful health signal.
    # "ok:False" here is overwhelmingly a NORMAL propose->refine outcome
    # (no_opportunity / non_answer / not_concrete / compile_fail / safety /
    #  diff_not_wholefile) — the local model simply had nothing worth
    # queueing this cycle. Those are successes for a run-to-completion
    # oneshot; only a real error (CEO cockpit unreachable) should fail.
    if out.get("ok"):
        return 0
    reason = str(out.get("reason", ""))
    INFRA_ERRORS = ("unreachable",)
    return 1 if reason in INFRA_ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
