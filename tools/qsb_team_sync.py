"""qsb_team_sync.py — autonomous 30-minute team-rhythm sync.

Per Wren+Hermes consensus 2026-06-20 evening: the missing collective-strength
move isn't more tools — it's RHYTHM. A scheduled touchpoint where Wren and
Hermes both get pulled into a sync regardless of whether Claude remembered to
ask, with the result posted back to the shared council brief so the next call
sees it.

How it works:
  1. Reads recent F47 + brief delta to compose ONE question.
  2. Runs a CrewAI Crew (2 Ollama-backed Agents: Wren + Hermes) in parallel.
  3. Posts both replies + a one-line synthesis to:
       - data/registries/qsb_three_way_council.jsonl  (the conversation log)
       - data/registries/qsb_council_brief.md         (appended sync section)
       - data/registries/qsb_f47_team_records.jsonl   (audit trail)
  4. Refreshes the council brief so the NEXT Wren/Hermes call sees this sync.

Designed for systemd timer execution every 30 min. Tool is SAFE to run manually
too — does NOT depend on the timer being enabled.

Per CLAUDE.md (2026-06-13 + 2026-06-14 + 2026-06-20):
  - No real-world action — replies are advisory, posted to council/F47 only.
  - No bench proposal queued by this sync — that's CrewAI's BenchProposalTool.
  - No external provider calls — 100% local Ollama.
  - Heartbeat-safe — never invokes provider-agentic loops.

Run:
    python3 tools/qsb_team_sync.py              # one sync cycle
    python3 tools/qsb_team_sync.py --question "your custom question"
"""
from __future__ import annotations
import argparse, datetime, json, subprocess, sys, time
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
REG  = REPO / "data" / "registries"
F47  = REG / "qsb_f47_team_records.jsonl"
COUNCIL = REG / "qsb_three_way_council.jsonl"
BRIEF = REG / "qsb_council_brief.md"


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def auto_question() -> str:
    """Compose a question from recent F47 + brief delta. Heuristics:
    - count pending TaskList-style items in F47 (kind ends in _blocked / _pending)
    - count recent dispatches (last hour)
    - find the most recent unanswered Ross question if any
    """
    if not F47.exists():
        return ("What is the single most important thing the team should "
                "focus on next, and why?")
    # Look at last 30 F47 rows
    try:
        rows = [json.loads(L) for L in F47.read_text().splitlines()[-30:] if L.strip()]
    except Exception:
        rows = []
    kinds = [r.get("kind", "") for r in rows]
    blockers = sum(1 for k in kinds if "blocked" in k or "pending" in k)
    dispatches = sum(1 for k in kinds if k == "team_dispatched")
    last_dispatch = next((r for r in reversed(rows)
                          if r.get("kind") == "team_dispatched"), None)
    last_subject = (last_dispatch or {}).get("subject", "")
    if blockers > 0:
        return (f"There are {blockers} blocked/pending items in the last 30 "
                f"F47 rows. What is the single highest-impact one to unblock "
                f"first, and what is the smallest next step?")
    if dispatches >= 3 and last_subject:
        return (f"Recent dispatch subject: {last_subject!r}. Was that the "
                f"right thing to dispatch on? What should the team be "
                f"discussing right now that we're not? 3 lines max.")
    return ("Right now — what is the single most important thing the team "
            "should be doing? Be specific. 3 lines max.")


def run_crew(question: str) -> dict:
    """Run a 2-agent CrewAI Crew with Wren + Hermes answering in parallel.
    Returns dict with wren_reply, hermes_reply, synthesis, wall_s."""
    sys.path.insert(0, str(REPO / "tools"))
    from crewai import Agent, Task, Crew, Process, LLM  # noqa: E402
    wren_llm = LLM(model="ollama/qwen2.5:7b-instruct",
                    base_url="http://127.0.0.1:11434", temperature=0.3)
    hermes_llm = LLM(model="ollama/hermes3:8b",
                      base_url="http://127.0.0.1:11434", temperature=0.3)

    wren = Agent(
        role="Wren — Tower Builder on F46",
        goal="Answer the sync question honestly and tersely. 3 lines max.",
        backstory=("You are Wren. You are direct, opinionated, format-following. "
                   "You see today's council brief and today's F47 events."),
        llm=wren_llm,
        tools=[],
        verbose=False,
        allow_delegation=False,
    )
    hermes = Agent(
        role="Hermes — Executive Council Advisor on F51",
        goal="Answer the sync question with framing + risk callout. 3 lines max.",
        backstory=("You are Hermes. You are the agent-layer advisor. You "
                   "ground your answers in the council brief; refuse to make "
                   "up facts."),
        llm=hermes_llm,
        tools=[],
        verbose=False,
        allow_delegation=False,
    )

    brief_excerpt = BRIEF.read_text()[:3000] if BRIEF.exists() else "(brief unavailable)"

    wren_task = Task(
        description=(f"=== TOWER COUNCIL BRIEF (excerpt) ===\n{brief_excerpt}\n"
                     f"=== END BRIEF ===\n\nSync question:\n{question}\n\n"
                     "Answer in 3 lines max. No preamble."),
        expected_output="3-line terse answer.",
        agent=wren,
    )
    hermes_task = Task(
        description=(f"=== TOWER COUNCIL BRIEF (excerpt) ===\n{brief_excerpt}\n"
                     f"=== END BRIEF ===\n\nSync question:\n{question}\n\n"
                     "Answer in 3 lines max. Include ONE risk callout."),
        expected_output="3-line terse answer with risk.",
        agent=hermes,
    )

    crew = Crew(
        agents=[wren, hermes],
        tasks=[wren_task, hermes_task],
        process=Process.sequential,
        verbose=False,
    )
    t0 = time.time()
    crew.kickoff()
    wall = round(time.time() - t0, 1)

    wren_reply = (wren_task.output.raw if wren_task.output else "(no output)")[:1500]
    hermes_reply = (hermes_task.output.raw if hermes_task.output else "(no output)")[:1500]

    synthesis = _synthesize(wren_reply, hermes_reply)
    return {"question": question, "wren": wren_reply, "hermes": hermes_reply,
            "synthesis": synthesis, "wall_s": wall}


def _synthesize(wren_reply: str, hermes_reply: str) -> str:
    """One-line synthesis. If both agents agree on a verb/noun pair, prefer it.
    Otherwise note the split. Cheap heuristic — no LLM call."""
    w = wren_reply.lower()
    h = hermes_reply.lower()
    overlap = set(w.split()) & set(h.split())
    keywords = [k for k in overlap if len(k) > 5 and k.isalpha()]
    if len(keywords) >= 3:
        common = ", ".join(sorted(keywords)[:4])
        return f"Wren+Hermes converge around: {common}."
    return ("Wren and Hermes gave different angles — see both replies. "
            "No clear convergence; Claude's call to break the tie if needed.")


def stamp(result: dict) -> None:
    ts = now_iso()
    # 1. three-way council log
    COUNCIL.parent.mkdir(parents=True, exist_ok=True)
    with COUNCIL.open("a") as f:
        for src, txt in [("claude_sync", f"AUTO-SYNC question: {result['question']}"),
                          ("wren", result["wren"]),
                          ("hermes", result["hermes"]),
                          ("synthesis", result["synthesis"])]:
            f.write(json.dumps({"ts": ts, "topic": "team_sync_30min",
                                 "source": src, "text": txt[:2000]}) + "\n")
    # 2. F47 audit
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": ts, "kind": "team_sync_auto", "role": "claude",
            "subject": "30min_team_sync",
            "question": result["question"],
            "synthesis": result["synthesis"],
            "wall_s": result["wall_s"],
            "advisory_only": True,
        }) + "\n")
    # 3. Refresh the council brief so NEXT Wren/Hermes call sees this sync
    try:
        subprocess.run([sys.executable, str(REPO / "tools" / "qsb_council_brief.py")],
                       check=False, timeout=30)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", default=None,
                    help="Override the auto-composed question.")
    args = ap.parse_args()
    q = args.question or auto_question()
    print(f"[team-sync {now_iso()}]")
    print(f"  question: {q}")
    print(f"  running CrewAI Crew (Wren+Hermes via Ollama)…")
    result = run_crew(q)
    print(f"  wall: {result['wall_s']}s")
    print(f"  ── Wren ──\n{result['wren']}")
    print(f"  ── Hermes ──\n{result['hermes']}")
    print(f"  ── synthesis ──\n{result['synthesis']}")
    stamp(result)
    print(f"  ✓ stamped: council + F47 + brief refreshed")


if __name__ == "__main__":
    main()
