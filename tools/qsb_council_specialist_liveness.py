#!/usr/bin/env python3
"""qsb_council_specialist_liveness.py — recurring REAL-work liveness driver for the
council specialist stations on the Underground transit map (:8875).

WHAT THIS IS (honest framing):
  This is a liveness / warmup prober, the SAME pattern as tools/qsb_wren_ceo_health.py
  (which keeps the provider CEO stations lit by making a real round-trip). Here we
  keep the LOCAL council-specialist stations lit by handing each specialist a tiny,
  genuine task and — ONLY when it actually responds — appending the real
  `tool_selected` (or sandbox) event that the map already reads.

  The map (tools/qsb_tower_transit_map.py) lights these stations from
  data/registries/qsb_council_tasks.jsonl:
    · a `tool_selected` event whose `text` names the specialist:
        _tool_station() substrings:  "iquest"->iquest_40b, "hermes"->hermes,
                                      "claude"->claude_acct, "qwen"->qwen_worker
    · `sandbox_passed` / `sandbox_rejected` -> tc_sandbox
  Age-gate = 900s, so a run every ~6 min keeps them freshly lit.

NEVER FABRICATE: an event is written ONLY when the specialist produced real output
(or the sandbox produced a real verdict). If a model is dead / doesn't answer, we
SKIP it and log why. Nothing false ever lands in the board.

APPEND FORMAT — reused verbatim from the task-council autorunner
(tools/qsb_task_council_autorunner.py journal(...) at the tool_selected call):
    {"ts": utc(), "event": "tool_selected", "task_id": tid, "actor": "wren",
     "text": f"owner uses {tool} ({model})"}
We append via the same helper style (open board, write json line) to the same path
data/registries/qsb_council_tasks.jsonl. Sandbox events reuse the shape emitted by
qsb_council_tasks.sandbox_pass / the sandbox_rejected branch:
    {"ts": utc(), "event": "sandbox_passed"|"sandbox_rejected", "task_id": tid,
     "actor": ..., "text": ...}
"""
from __future__ import annotations
import os, sys, json, uuid, time, tempfile, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BOARD = ROOT / "data/registries/qsb_council_tasks.jsonl"
TOOLS_DIR = ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))


def utc() -> str:
    # matches qsb_task_council_run.utc() / qsb_council_tasks.utc()
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def journal(ev: dict) -> None:
    """Reuse the autorunner/council append: append-only JSON line to the board."""
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    with BOARD.open("a") as f:
        f.write(json.dumps(ev) + "\n")


def _tool_selected(tid: str, tool: str, model: str) -> None:
    """Exact autorunner format: 'owner uses {tool} ({model})'."""
    journal({"ts": utc(), "event": "tool_selected", "task_id": tid, "actor": "wren",
             "text": f"owner uses {tool} ({model})"})


def _log(results: list, station: str, lit: bool, note: str) -> None:
    results.append({"station": station, "lit": lit, "note": note})
    tag = "LIT " if lit else "SKIP"
    print(f"  [{tag}] {station}: {note}", flush=True)


# ---------------------------------------------------------------------------
def drive_iquest(tid: str, results: list, TOOLS) -> None:
    """iquest_40b — tiny real coder task via use_tool(kind=coder) -> iQuest-40B."""
    station = "iquest_40b"
    # Probe endpoint first; the 40B on CPU can hang for hours per its own tool's note.
    if not TOOLS._ollama_generate_alive("iquest-coder-v1:40b-instruct", timeout_s=6.0):
        _log(results, station, False, "iQuest-40B endpoint did not answer probe — skipped honestly")
        return
    tool = {"kind": "coder", "tool": "iQuest-40B", "model": "iquest-coder-v1:40b-instruct"}
    try:
        r = TOOLS.use_tool(tool, "Write a Python function is_even(n) that returns True if n is even.",
                           timeout_s=180)
    except Exception as e:
        _log(results, station, False, f"use_tool(coder) raised: {str(e)[:120]}")
        return
    out = (r.get("output") or "").strip()
    if r.get("ok") and out:
        _tool_selected(tid, "iQuest-40B", r.get("model") or tool["model"])
        _log(results, station, True, f"REAL {r.get('model')}: {out[:120]!r}")
    else:
        _log(results, station, False, f"no real output (ok={r.get('ok')}, err={str(r.get('error'))[:100]})")


def drive_hermes(tid: str, results: list, TOOLS) -> None:
    """hermes — tiny real reasoning via the hermes ollama model."""
    station = "hermes"
    model = "hermes3:8b"  # HONEST: local hermes is the 8b, not 70b
    if not TOOLS._ollama_generate_alive(model, timeout_s=8.0):
        _log(results, station, False, f"{model} endpoint did not answer probe — skipped honestly")
        return
    tool = {"kind": "reasoning", "tool": "Hermes", "model": model}
    try:
        r = TOOLS.use_tool(tool, "In one short sentence: name one risk of shipping code without tests.",
                           timeout_s=60)
    except Exception as e:
        _log(results, station, False, f"use_tool(reasoning) raised: {str(e)[:120]}")
        return
    out = (r.get("output") or "").strip()
    if r.get("ok") and out:
        # be honest about the exact tag that ran
        _tool_selected(tid, "Hermes", r.get("model") or model)
        _log(results, station, True, f"REAL {r.get('model')}: {out[:120]!r}")
    else:
        _log(results, station, False, f"no real output (ok={r.get('ok')}, err={str(r.get('error'))[:100]})")


def drive_qwen(tid: str, results: list, TOOLS) -> None:
    """qwen_worker — tiny real research via qwen2.5:14b."""
    station = "qwen_worker"
    model = "qwen2.5:14b"
    if not TOOLS._ollama_generate_alive(model, timeout_s=8.0):
        _log(results, station, False, f"{model} endpoint did not answer probe — skipped honestly")
        return
    tool = {"kind": "general", "tool": "qwen worker", "model": model}
    try:
        r = TOOLS.use_tool(tool, "In one short line: name a common Python web framework.", timeout_s=60)
    except Exception as e:
        _log(results, station, False, f"use_tool(general) raised: {str(e)[:120]}")
        return
    out = (r.get("output") or "").strip()
    if r.get("ok") and out:
        _tool_selected(tid, "qwen worker", r.get("model") or model)
        _log(results, station, True, f"REAL {r.get('model')}: {out[:120]!r}")
    else:
        _log(results, station, False, f"no real output (ok={r.get('ok')}, err={str(r.get('error'))[:100]})")


def drive_claude(tid: str, results: list, TOOLS) -> None:
    """claude_acct — tiny real task via the caged Claude account CLI (ANTHROPIC_API_KEY unset).
    Skip honestly if the caged CLI is unavailable."""
    station = "claude_acct"
    if not shutil.which("claude"):
        _log(results, station, False, "caged Claude CLI ('claude') not on PATH — skipped honestly")
        return
    tool = {"kind": "specialist", "tool": "Claude", "model": "claude-account(Max)"}
    try:
        r = TOOLS.use_tool(tool, "print('hello from the caged specialist')  # just return this one line",
                           timeout_s=120)
    except Exception as e:
        _log(results, station, False, f"use_tool(specialist) raised: {str(e)[:120]}")
        return
    out = (r.get("output") or "").strip()
    if r.get("ok") and out:
        _tool_selected(tid, "Claude", r.get("model") or "claude-account(Max)")
        _log(results, station, True, f"REAL claude-account: {out[:120]!r}")
    else:
        _log(results, station, False,
             f"caged Claude returned no usable code (ok={r.get('ok')}, err={str(r.get('error'))[:100]}) — skipped")


def drive_sandbox(tid: str, results: list) -> None:
    """tc_sandbox — queue a REAL valid-python proposal and run qsb_proposal_sandbox on it,
    mirroring the REAL verdict as sandbox_passed / sandbox_rejected. Uses a /tmp queue so
    nothing is left in the repo tree."""
    station = "tc_sandbox"
    import qsb_proposal_sandbox as SB
    pid = "liveness_" + uuid.uuid4().hex[:10]
    valid_py = "def is_even(n):\n    return n % 2 == 0\n"
    proposal = {
        "id": pid,
        "ts": utc(),
        "target_files": ["scratch/liveness_probe.py"],
        # file_replacements content is only ever written into a /tmp sandbox dir by the tool,
        # never into the repo — verified in run_sandbox().
        "file_replacements": {"scratch/liveness_probe.py": valid_py},
        "note": "council specialist liveness probe (auto)",
    }
    # Point the sandbox's queue reader at a throwaway /tmp file so we leave NOTHING in the repo.
    tmp_queue = Path(tempfile.gettempdir()) / f"qsb_liveness_queue_{pid}.jsonl"
    tmp_queue.write_text(json.dumps(proposal) + "\n")
    orig_pq, orig_p = SB.PROPOSAL_QUEUE, SB.PROPOSALS
    try:
        SB.PROPOSAL_QUEUE = tmp_queue
        SB.PROPOSALS = tmp_queue  # both point at the throwaway; load_proposal matches by id
        rec = SB.run_sandbox(pid)
    except Exception as e:
        _log(results, station, False, f"run_sandbox raised: {str(e)[:120]}")
        return
    finally:
        SB.PROPOSAL_QUEUE, SB.PROPOSALS = orig_pq, orig_p
        try:
            tmp_queue.unlink()
        except Exception:
            pass
        # clean the /tmp sandbox dir the tool created
        sbdir = rec.get("sandbox_dir") if isinstance(rec, dict) else None
        if sbdir and str(sbdir).startswith(tempfile.gettempdir()):
            shutil.rmtree(sbdir, ignore_errors=True)

    verdict = rec.get("verdict")
    if verdict == "green":
        journal({"ts": utc(), "event": "sandbox_passed", "task_id": tid, "actor": "tc_sandbox",
                 "text": f"liveness proposal {pid} py_compile green (real sandbox verdict)"})
        _log(results, station, True, f"REAL sandbox verdict green ({rec.get('smokes')})")
    elif verdict == "red":
        journal({"ts": utc(), "event": "sandbox_rejected", "task_id": tid, "actor": "tc_sandbox",
                 "text": f"liveness proposal {pid} py_compile red (real sandbox verdict)"})
        _log(results, station, True, f"REAL sandbox verdict red ({rec.get('smokes')})")
    else:
        _log(results, station, False, f"sandbox gave non-pass/reject verdict={verdict!r} — no event written")


# ---------------------------------------------------------------------------
def main() -> int:
    print(f"[{utc()}] council-specialist liveness run starting", flush=True)
    import qsb_council15_tools as TOOLS
    tid = "LIVE_" + uuid.uuid4().hex[:10]
    results: list = []

    drive_iquest(tid, results, TOOLS)
    drive_hermes(tid, results, TOOLS)
    drive_qwen(tid, results, TOOLS)
    drive_claude(tid, results, TOOLS)
    drive_sandbox(tid, results)

    lit = [r["station"] for r in results if r["lit"]]
    skipped = [r["station"] for r in results if not r["lit"]]
    print(f"[{utc()}] done — LIT={lit} SKIPPED={skipped}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
