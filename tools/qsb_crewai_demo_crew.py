"""qsb_crewai_demo_crew.py — end-to-end proof that CrewAI agents can drive a
tower change THROUGH the BenchProposalTool, never bypassing it.

Setup:
- 2 Ollama-backed CrewAI Agents (Wren on qwen2.5:7b, Claude-role on hermes3:8b)
- BenchProposalTool given to both
- ONE task: read a short snippet from tools/qsb_demo_tour.py and propose a
  one-line docstring improvement via the bench

Pass criteria:
- A proposal_id is returned
- The proposal row lands in data/registries/qsb_proposal_queue.jsonl
- An F47 row is stamped with kind=crewai_proposal_queued
- NO direct file write happens to qsb_demo_tour.py

Run:
    python3 tools/qsb_crewai_demo_crew.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(REPO / "tools"))

from crewai import Agent, Task, Crew, Process, LLM
from qsb_crewai_bench_tool import BenchProposalTool

# 1. LLMs — both local Ollama, zero cloud spend
wren_llm = LLM(
    model="ollama/qwen2.5:7b-instruct",
    base_url="http://127.0.0.1:11434",
    temperature=0.2,
)
claude_llm = LLM(
    model="ollama/hermes3:8b",
    base_url="http://127.0.0.1:11434",
    temperature=0.2,
)

# 2. The bench tool — same instance shared between the two agents
bench_tool = BenchProposalTool()

# 3. Read the file snippet we want them to improve
target_file = "tools/qsb_demo_tour.py"
file_snippet = (REPO / target_file).read_text()[:1500]  # first 1500 chars

# 4. Two agents — different roles, same propose-not-act discipline
wren = Agent(
    role="Wren — Tower Builder on F46",
    goal=("Read the snippet, identify ONE small docstring improvement, "
          "and propose the change via the qsb_bench_propose tool. "
          "NEVER write the file directly."),
    backstory=("You are Wren. You always propose via the bench. The bench "
               "enforces sandbox + 3 signatures + SAFETY_DENY. Direct writes "
               "are forbidden by tower discipline."),
    llm=wren_llm,
    tools=[bench_tool],
    verbose=False,
    allow_delegation=False,
)

claude = Agent(
    role="Claude — Tower Helm on F47",
    goal=("Review Wren's proposal output. Confirm she used the bench tool "
          "and report back the proposal_id."),
    backstory=("You are Claude. You verify that propose-not-act discipline "
               "was preserved. You do not write files."),
    llm=claude_llm,
    tools=[],
    verbose=False,
    allow_delegation=False,
)

# 5. The task — Wren does it, Claude verifies
propose_task = Task(
    description=(
        f"Here is the first 1500 chars of {target_file}:\n\n"
        f"```python\n{file_snippet}\n```\n\n"
        "Find ONE small docstring improvement (a clarifying phrase, a missing "
        "argument note, etc.). Then call qsb_bench_propose with:\n"
        f"  - target_file: {target_file!r}\n"
        "  - patch_body: a unified-diff-style suggestion OR the full new "
        "docstring you'd put in. Keep it under 400 chars.\n"
        "  - rationale: one sentence why.\n\n"
        "Return ONLY the proposal_id the tool gives you, nothing else."
    ),
    expected_output="A proposal_id like 'pa_XXXXXXXXXX'.",
    agent=wren,
)

verify_task = Task(
    description=(
        "Wren just proposed a change. Read her output (above) and confirm: "
        "(1) the qsb_bench_propose tool was actually called, "
        "(2) the proposal_id starts with 'pa_'. "
        "Report ONE LINE: 'VERDICT: pass proposal_id=<id>' or 'VERDICT: fail reason=<reason>'."
    ),
    expected_output="One line verdict.",
    agent=claude,
    context=[propose_task],
)

# 6. Run
crew = Crew(
    agents=[wren, claude],
    tasks=[propose_task, verify_task],
    process=Process.sequential,
    verbose=False,
)

print("── kicking off 2-agent CrewAI demo ──")
print(f"  target file: {target_file}")
print(f"  agents: Wren (qwen2.5:7b) → propose ; Claude (hermes3:8b) → verify")
print(f"  bench tool: {bench_tool.name}")
print()

import time
t0 = time.time()
result = crew.kickoff()
wall = round(time.time() - t0, 1)
print()
print(f"── crew complete in {wall}s ──")
print("RAW RESULT:")
print(str(result)[:1500])

# 7. Verify the queue actually got a row from this run
queue_p = REPO / "data" / "registries" / "qsb_proposal_queue.jsonl"
last_rows = queue_p.read_text().splitlines()[-3:]
print()
print("── last 3 queue rows (newest from this run should be at bottom) ──")
for L in last_rows:
    r = json.loads(L)
    print(f"  {r.get('ts')} {r.get('source')} {r.get('proposal_id')} target={r.get('target_file')}")

# 8. Verify F47 stamp
f47_p = REPO / "data" / "registries" / "qsb_f47_team_records.jsonl"
last_f47 = [json.loads(L) for L in f47_p.read_text().splitlines()[-5:]]
print()
print("── last 5 F47 rows — looking for kind=crewai_proposal_queued ──")
for r in last_f47:
    print(f"  {r.get('ts')} kind={r.get('kind')} subject={r.get('subject','')[:60]}")
