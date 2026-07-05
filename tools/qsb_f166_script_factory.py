"""qsb_f166_script_factory.py — F166 TikTok Studio: real-work content pipeline.

Per Wren+Hermes auto-sync 2026-06-20 evening: F166 is the highest-priority
unblock. This tool runs a 3-agent CrewAI Crew (Ringmaster + Writer + Judge)
to produce one 30-second AI-vs-AI battle script + SuperTonic voice clips +
queue the result as a bench proposal for Ross to approve before posting.

Self-improving loop (2026-06-20 evening, Ross "keep going"): if the judge
returns VERDICT=rewrite, the script is re-written with the judge's rationale
fed back into the writer's brief, up to --max-rounds times.

Per CLAUDE.md (still no autonomous posting): the script + clips land in
proof_of_work/2026-06-20/f166/ and qsb_proposal_queue.jsonl. Nothing posts
without Ross's signature on the proposal.

Run:
    python3 tools/qsb_f166_script_factory.py                # 3 rounds max
    python3 tools/qsb_f166_script_factory.py --max-rounds 5
"""
from __future__ import annotations
import argparse, datetime, json, re, sys, time
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(REPO / "tools"))
from crewai import Agent, Task, Crew, Process, LLM
from qsb_crewai_bench_tool import BenchProposalTool

TOPIC = "Open-source vs proprietary AI models in the tower"
PAYOFF = ("Wren reveals she uses BOTH: Ollama for daily work, bounded "
          "OpenAI/DeepSeek advisory for second opinions. The answer isn't "
          "either side — it's a blend with hard caps.")

TODAY = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
OUT_DIR = REPO / "proof_of_work" / TODAY / "f166"
OUT_DIR.mkdir(parents=True, exist_ok=True)
F47 = REPO / "data" / "registries" / "qsb_f47_team_records.jsonl"


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _judge_verdict(score_text: str) -> tuple[str, str]:
    """Return ('ship'|'rewrite', rationale). Default to 'rewrite' on parse fail."""
    m = re.search(r"VERDICT\s*=\s*(ship|rewrite)", score_text, re.I)
    verdict = (m.group(1).lower() if m else "rewrite")
    rationale = score_text.split("Rationale", 1)[-1] if "Rationale" in score_text else score_text
    return verdict, rationale.strip()[:600]


def _run_round(round_num: int, wren_llm, hermes_llm, judge_llm,
                prior_feedback: str = "") -> dict:
    ringmaster = Agent(
        role="F166 Ringmaster — Battle Picker",
        goal=("Frame the 30-second battle so it's TikTok-shaped: hook in 5s, "
              "back-and-forth in 15s, payoff in 10s. Be terse."),
        backstory="You set the structure. Writers fill it in.",
        llm=wren_llm, tools=[], verbose=False, allow_delegation=False,
    )
    writer = Agent(
        role="F166 Script Writer",
        goal=("Write a 30-second AI-vs-AI battle script alternating WREN: "
              "and HERMES: lines. Each line < 12 words. End with the agreed "
              "payoff line. Output only the script — no commentary."),
        backstory=("You are the F166 script writer. Wren is direct + pragmatic; "
                   "Hermes is analytical + principles-first. Lines should sound "
                   "like real disagreement, not strawman."),
        llm=hermes_llm, tools=[], verbose=False, allow_delegation=False,
    )
    judge = Agent(
        role="F166 Judge — Independent Commentator",
        goal=("Score the script on hook strength (1-5), payoff (1-5), and "
              "screenshot-worthiness (1-5). VERDICT=ship if HOOK + PAYOFF >= 8 "
              "AND SCREENSHOT >= 4. Otherwise VERDICT=rewrite with a one-line "
              "rationale a writer can act on."),
        backstory="You decide if the script ships or goes back for a rewrite.",
        llm=judge_llm, tools=[], verbose=False, allow_delegation=False,
    )
    feedback_block = (f"\n\nPRIOR-ROUND JUDGE FEEDBACK (rewrite this):\n"
                      f"{prior_feedback}\n\nFix the specific weakness above. "
                      f"Make the hook MORE punchy and the payoff MORE quotable.\n"
                      if prior_feedback else "")
    structure_task = Task(
        description=(
            f"Topic: {TOPIC}. Payoff: {PAYOFF}.\n"
            f"Round: {round_num}.{feedback_block}\n"
            "Output a 3-line outline:\n"
            "  HOOK (5s): <one sentence>\n"
            "  CONFLICT (15s): <one sentence>\n"
            "  PAYOFF (10s): <one sentence>\n"
            "Nothing else."
        ),
        expected_output="3-line outline.", agent=ringmaster,
    )
    write_task = Task(
        description=(
            f"Topic: {TOPIC}\nPayoff direction: {PAYOFF}\n{feedback_block}"
            "Use the outline. Write the full 30-second script:\n"
            "  WREN: ...\n  HERMES: ...\n  WREN: ...\n  HERMES: ...\n"
            "Each line < 12 words. Final line MUST be the payoff (Wren line). "
            "ONLY the script. No (12) parenthetical numbering."
        ),
        expected_output="Alternating WREN: / HERMES: script lines.",
        agent=writer, context=[structure_task],
    )
    judge_task = Task(
        description=(
            "Score in this format ONLY:\n"
            "  HOOK=<1-5> PAYOFF=<1-5> SCREENSHOT=<1-5> VERDICT=<ship|rewrite>\n"
            "Rationale: <one sentence — what to fix or why it ships>."
        ),
        expected_output="One-line score + rationale.",
        agent=judge, context=[write_task],
    )
    crew = Crew(agents=[ringmaster, writer, judge],
                tasks=[structure_task, write_task, judge_task],
                process=Process.sequential, verbose=False)
    t0 = time.time()
    crew.kickoff()
    wall = round(time.time() - t0, 1)
    outline = str(structure_task.output.raw)[:1500].strip()
    script = str(write_task.output.raw)[:2500].strip()
    score = str(judge_task.output.raw)[:600].strip()
    verdict, rationale = _judge_verdict(score)
    return {"round": round_num, "wall_s": wall, "outline": outline,
            "script": script, "score": score, "verdict": verdict,
            "rationale": rationale}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()

    wren_llm = LLM(model="ollama/qwen2.5:7b-instruct",
                    base_url="http://127.0.0.1:11434", temperature=0.5)
    hermes_llm = LLM(model="ollama/hermes3:8b",
                      base_url="http://127.0.0.1:11434", temperature=0.5)
    judge_llm = LLM(model="ollama/qwen2.5:7b-instruct",
                     base_url="http://127.0.0.1:11434", temperature=0.2)

    bench = BenchProposalTool()

    print(f"[f166-factory {now_iso()}]  topic: {TOPIC}  max_rounds: {args.max_rounds}")
    rounds = []
    feedback = ""
    final = None
    for n in range(1, args.max_rounds + 1):
        print(f"\n── round {n} ──")
        r = _run_round(n, wren_llm, hermes_llm, judge_llm, feedback)
        rounds.append(r)
        print(f"  wall: {r['wall_s']}s  verdict: {r['verdict']}  score: {r['score'][:120]}")
        if r["verdict"] == "ship":
            final = r
            break
        feedback = r["rationale"]
    if final is None:
        # took max rounds without ship — use the highest-scoring round
        def _score_sum(rr):
            m = re.findall(r"(?:HOOK|PAYOFF|SCREENSHOT)\s*=\s*(\d)", rr["score"])
            return sum(int(x) for x in m) if m else 0
        final = max(rounds, key=_score_sum)
        print(f"\n  ▸ max rounds hit — best of {len(rounds)} = round {final['round']}")

    outline = final["outline"]; script = final["script"]; score = final["score"]
    wall = sum(r["wall_s"] for r in rounds)

    print()
    print("── FINAL OUTLINE ──"); print(outline)
    print("\n── FINAL SCRIPT ──"); print(script)
    print("\n── FINAL JUDGE ──"); print(score)

    # Persist as proof — include all rounds for transparency
    bundle = OUT_DIR / "battle_01_open_vs_proprietary.md"
    rounds_md = "\n\n".join(
        f"### Round {r['round']} — {r['verdict']} ({r['wall_s']}s)\n"
        f"```\n{r['script']}\n```\nScore: {r['score']}"
        for r in rounds
    )
    bundle.write_text(
        f"# F166 Battle Script 01 — Open vs Proprietary\n\n"
        f"Generated: {now_iso()}\n"
        f"Topic: {TOPIC}\n"
        f"Payoff: {PAYOFF}\n"
        f"Rounds: {len(rounds)} · total wall: {wall}s · final: round {final['round']}\n\n"
        f"## Final outline\n{outline}\n\n## Final script\n```\n{script}\n```\n\n"
        f"## Final judge\n{score}\n\n## All rounds (self-improving loop)\n{rounds_md}\n"
    )
    print(f"\n  ✓ bundle → {bundle.relative_to(REPO)}")

    # Render the voices via SuperTonic
    print("\n── rendering voices via /api/tts ──")
    import urllib.request, urllib.error
    wren_lines = [L.split("WREN:", 1)[1].strip() for L in script.splitlines()
                  if "WREN:" in L][:6]
    hermes_lines = [L.split("HERMES:", 1)[1].strip() for L in script.splitlines()
                    if "HERMES:" in L][:6]

    def _tts(line: str, voice: str, out: Path):
        body = json.dumps({"text": line, "voice": voice}).encode()
        req = urllib.request.Request("http://127.0.0.1:8765/api/tts",
                                      data=body, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out.write_bytes(r.read())

    for i, line in enumerate(wren_lines):
        out = OUT_DIR / f"battle_01_wren_{i+1:02d}.wav"
        try: _tts(line, "F1", out); print(f"  WREN  {i+1}: {out.name}  ({line[:50]}…)")
        except Exception as e: print(f"  WREN  {i+1}: FAIL {e}")
    for i, line in enumerate(hermes_lines):
        out = OUT_DIR / f"battle_01_hermes_{i+1:02d}.wav"
        try: _tts(line, "M2", out); print(f"  HERMES {i+1}: {out.name}  ({line[:50]}…)")
        except Exception as e: print(f"  HERMES {i+1}: FAIL {e}")

    # Queue a bench proposal so Ross signs before this ever posts
    proposal_msg = (
        f"target_file: proof_of_work/{TODAY}/f166/battle_01_open_vs_proprietary.md\n"
        f"action: review F166 battle script + voice clips for first post.\n"
        f"judge_score: {score}\n"
    )
    pid_msg = bench._run(
        target_file=f"proof_of_work/{TODAY}/f166/battle_01_open_vs_proprietary.md",
        patch_body=proposal_msg,
        rationale="F166 first-real-script for Ross approval before any TikTok post."
    )
    print(f"\n  ✓ bench: {pid_msg}")

    # F47 stamp
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "kind": "f166_real_work_dispatched", "role": "claude",
            "subject": "battle_01_open_vs_proprietary",
            "detail": (f"3-agent CrewAI Crew produced first F166 TikTok battle "
                       f"script + SuperTonic voice clips. Bundle at "
                       f"{bundle.relative_to(REPO)}. Proposal queued for Ross "
                       f"approval BEFORE any post. Wall={wall}s."),
            "judge_score": score[:200],
            "advisory_only": True,
        }) + "\n")
    print("  ✓ F47 stamped kind=f166_real_work_dispatched")


if __name__ == "__main__":
    main()
