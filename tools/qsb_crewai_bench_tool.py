"""qsb_crewai_bench_tool.py — CrewAI Tool adapter for the tower's multi-sig bench.

Per the team-conversation 2026-06-20 (Wren + Hermes both picked CrewAI for the
tower orchestration layer): CrewAI agents assume they can ACT directly. The
tower discipline says agents PROPOSE, the bench acts after sandbox + 3 sigs.

This adapter wraps `tool_qsb_propose_patch` from qsb_provider_agent.py so a
CrewAI Agent can `.execute` a "make this code change" intent and the result
is a proposal queued for the bench, never a direct write. The same multi-sig
rules in CLAUDE.md (2026-06-13 + sandbox + SAFETY_DENY paths) apply.

Works WITHOUT crewai installed — falls back to a duck-type so the architecture
can be smoke-tested before the heavy install (~250MB chromadb+lancedb+openai).
When crewai IS installed, the real BaseTool is used.

Usage from a CrewAI Crew (once crewai is installed):

    from tools.qsb_crewai_bench_tool import BenchProposalTool

    bench_tool = BenchProposalTool()

    coder = Agent(
        role="Tower Coder",
        goal="Patch tower files for bug fixes",
        backstory="Always proposes via the bench, never writes direct.",
        tools=[bench_tool],
        llm=...  # any Ollama-backed model
    )

Direct smoke (without crewai):
    python3 tools/qsb_crewai_bench_tool.py --smoke
"""
from __future__ import annotations
import json, sys, uuid, datetime
from pathlib import Path

# ── 1. Try the real CrewAI BaseTool. Duck-type if absent. ─────────────────
try:
    from crewai.tools import BaseTool as _CrewBaseTool  # type: ignore
    from pydantic import BaseModel, Field             # crewai pulls pydantic in
    _CREWAI_AVAILABLE = True
except Exception:
    _CREWAI_AVAILABLE = False

    class _CrewBaseTool:                              # duck-type stand-in
        """Stub of crewai.tools.BaseTool for shape-validation before install."""
        name: str = ""
        description: str = ""

        def _run(self, *args, **kwargs):              # what subclass overrides
            raise NotImplementedError

        def run(self, *args, **kwargs):
            return self._run(*args, **kwargs)


# ── 2. Pull the existing tower propose API. ──────────────────────────────
REPO = Path("/vaults/nvme0/qsb_tower_v1")
REG  = REPO / "data" / "registries"
F47  = REG / "qsb_f47_team_records.jsonl"
SAFETY_DENY = (
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


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue_proposal(target_file: str, patch_body: str, rationale: str) -> dict:
    """Queue a proposal — same row shape as tool_qsb_propose_patch but with
    a `via=crewai_bench_tool` marker so the bench can tell who routed it."""
    if not target_file or not patch_body:
        return {"ok": False, "error": "target_file and patch_body required"}
    # SAFETY_DENY check — refuse before we even touch the queue.
    if any(deny in target_file for deny in SAFETY_DENY) or ".." in target_file:
        return {"ok": False, "error": f"SAFETY_DENY: {target_file} cannot be proposed via tool"}
    pid = f"pa_{uuid.uuid4().hex[:10]}"
    row = {
        "ts": _now(),
        "proposal_id": pid,
        "source": "crewai_bench_tool",
        "target_file": target_file,
        "patch_body": patch_body[:8000],
        "rationale": rationale[:1000],
        "status": "queued_unsigned",
    }
    queue_p = REG / "qsb_proposal_queue.jsonl"
    queue_p.parent.mkdir(parents=True, exist_ok=True)
    with queue_p.open("a") as f:
        f.write(json.dumps(row) + "\n")
    # F47 stamp
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": _now(),
            "kind": "crewai_proposal_queued",
            "role": "bench_tool",
            "subject": pid,
            "detail": f"CrewAI agent queued proposal for {target_file}. Needs sandbox + 3 sigs to apply.",
            "advisory_only": True,
        }) + "\n")
    return {"ok": True, "proposal_id": pid,
            "message": f"queued proposal_id={pid} (needs sandbox + 3 sigs)"}


# ── 3. The CrewAI Tool. ──────────────────────────────────────────────────
class BenchProposalTool(_CrewBaseTool):
    """A CrewAI Tool that turns an agent's 'change this file' intent into a
    bench-queued proposal. The bench still enforces sandbox + 3 sigs +
    SAFETY_DENY before any patch lands. This is the seam that preserves the
    propose-not-act discipline when CrewAI is driving the loop."""

    name: str = "qsb_bench_propose"
    description: str = (
        "Queue a code change proposal to the QSB Tower bench. "
        "Arguments: target_file (str, relative path), patch_body (str, full "
        "new file content or unified diff), rationale (str, short reason). "
        "Returns a proposal_id. The change does NOT apply immediately — it "
        "must pass sandbox + collect 3 signatures from "
        "{coders_team, team_assistants, wren_crew, wren_herself, ross}."
    )

    def _run(self, target_file: str = "", patch_body: str = "",
             rationale: str = "") -> str:
        result = _queue_proposal(target_file, patch_body, rationale)
        if not result["ok"]:
            return f"ERROR: {result['error']}"
        return result["message"]


# ── 4. Smoke. ────────────────────────────────────────────────────────────
def _smoke():
    print(f"crewai available: {_CREWAI_AVAILABLE}")
    t = BenchProposalTool()
    print(f"BenchProposalTool name: {t.name!r}")
    print(f"BenchProposalTool description: {t.description[:80]}…")
    # 1. happy path
    r1 = t._run(
        target_file="tools/qsb_demo_target.py",
        patch_body="# smoke test patch — not real\nprint('hello bench')\n",
        rationale="CrewAI bench-tool smoke from qsb_crewai_bench_tool.py",
    )
    print("HAPPY:", r1)
    # 2. SAFETY_DENY check
    r2 = t._run(
        target_file="CLAUDE.md",
        patch_body="malicious",
        rationale="should be refused",
    )
    print("DENY:", r2)
    # 3. missing args
    r3 = t._run(target_file="", patch_body="", rationale="empty")
    print("EMPTY:", r3)
    # 4. tail the queue + F47 to prove the writes landed
    qpath = REG / "qsb_proposal_queue.jsonl"
    if qpath.exists():
        tail = qpath.read_text().splitlines()[-1]
        print("QUEUE-TAIL:", tail[:200])


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        _smoke()
    else:
        print(__doc__)
