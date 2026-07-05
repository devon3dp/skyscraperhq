#!/usr/bin/env python3
"""qsb_wren_chain_orchestrator.py — Wren multi-stage chain orchestrator (2026-07-03).

Ross verbatim: smoke test showed gemma4:12b compresses 4-stage prompts into
one tool call, so 4-stage smoke tests fail. Path C: chain single-stage
cycles. Each stage runs as its own Wren dispatch. State from prior stages
gets threaded into the next stage's prompt as CONTEXT. When the last stage
finishes, the chain writes a final verdict row.

Chain spec (JSON):
    {
        "id": "smoke_dash_redesign",
        "title": "Full dash redesign smoke test",
        "stages": [
            {"kind": "design",  "prompt": "Write your design concept to data/wren_sandbox/new_dash_concept.md..."},
            {"kind": "forge",   "prompt": "Dispatch Forge for HTML+CSS scaffold..."},
            {"kind": "pip",     "prompt": "Dispatch Pip for a 2-line summary..."},
            {"kind": "mira",    "prompt": "Dispatch Mira to review Forge's output..."},
            {"kind": "smoke",   "prompt": "wren_bash to verify sandbox file syntax..."},
            {"kind": "verdict", "prompt": "State PROMOTED or HELD..."}
        ]
    }

Chain state at data/registries/qsb_wren_chains.jsonl (one row per chain):
    {
        "id": "smoke_dash_redesign",
        "title": "...",
        "created_at": "...",
        "current_stage": 0,
        "stages": [{prompt, done, output, ts, session_id, wall_s}],
        "status": "pending | running | complete | blocked",
        "final_verdict": ""
    }

Run:
    python3 tools/qsb_wren_chain_orchestrator.py --new-file <spec.json>
    python3 tools/qsb_wren_chain_orchestrator.py --progress <chain_id>
    python3 tools/qsb_wren_chain_orchestrator.py --run-all <chain_id>   # progress until done
    python3 tools/qsb_wren_chain_orchestrator.py --status
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CHAINS = ROOT / "data/registries/qsb_wren_chains.jsonl"
WREN_AGENT = ROOT / "tools/qsb_wren_local_agent.py"

STAGE_TIMEOUT = 180  # sec per stage
MAX_CONTEXT_CHARS = 3000  # cap prior-stage summary threaded into next prompt


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_chains() -> list:
    if not CHAINS.exists(): return []
    out = []
    for l in CHAINS.read_text(errors="ignore").splitlines():
        try: out.append(json.loads(l))
        except Exception: continue
    return out


def _save_chains(chains: list):
    CHAINS.parent.mkdir(parents=True, exist_ok=True)
    with CHAINS.open("w") as f:
        for c in chains:
            f.write(json.dumps(c) + "\n")


def _find_chain(chain_id: str, chains: list) -> dict | None:
    for c in chains:
        if c.get("id") == chain_id: return c
    return None


def new_chain(spec: dict) -> dict:
    chains = _load_chains()
    if _find_chain(spec["id"], chains):
        raise SystemExit(f"chain {spec['id']!r} already exists")
    chain = {
        "id": spec["id"],
        "title": spec.get("title", spec["id"]),
        "created_at": utc_iso(),
        "current_stage": 0,
        "stages": [{
            "kind": s.get("kind", f"stage_{i}"),
            # 2026-07-03: claude_verify stages carry command/shell_cmd instead
            # of prompt — pass through whatever the spec gave us.
            "prompt": s.get("prompt", ""),
            "command": s.get("command"),
            "shell_cmd": s.get("shell_cmd"),
            "expect_exit": s.get("expect_exit", 0),
            "expect_contains": s.get("expect_contains"),
            "done": False,
            "output": "",
            "ts": None,
            "session_id": "",
            "wall_s": 0,
        } for i, s in enumerate(spec["stages"])],
        "status": "pending",
        "final_verdict": "",
    }
    chains.append(chain)
    _save_chains(chains)
    return chain


def _build_stage_prompt(chain: dict, stage_idx: int) -> str:
    """Thread prior stage outputs into this stage's prompt as CONTEXT."""
    stage = chain["stages"][stage_idx]
    prior_ctx = ""
    if stage_idx > 0:
        parts = []
        for i in range(stage_idx):
            s = chain["stages"][i]
            out = (s.get("output") or "")[:600]
            parts.append(f"[stage {i} · {s.get('kind','?')}]\n{out}")
        prior_ctx = "\n\n".join(parts)[:MAX_CONTEXT_CHARS]
    wrapped = (
        f"CHAIN {chain['id']!r} — stage {stage_idx+1}/{len(chain['stages'])} · kind={stage['kind']}\n"
        f"\nTHIS STAGE'S JOB (do only this stage, nothing else):\n{stage['prompt']}\n"
    )
    if prior_ctx:
        wrapped += (
            f"\n---\nPRIOR STAGES CONTEXT (what already happened — read but do not "
            f"repeat their work):\n{prior_ctx}\n"
        )
    wrapped += (
        f"\n---\nFORMAT: perform the stage, then end with a ONE-LINE STAGE_OUT: "
        f"summary of what you did/found so the next stage can pick up. Nothing else."
    )
    return wrapped


def _run_claude_verify(stage: dict) -> tuple[str, bool]:
    """2026-07-03 — deterministic Claude-side verify. Runs subprocess directly
    (NO Wren dispatch), inspects exit code + stdout. Returns (output, passed).

    Stage spec:
        {"kind":"claude_verify",
         "command": ["python3","-c","..."],   OR  "shell_cmd": "python3 -c '...'"
         "expect_exit": 0,                    (default 0)
         "expect_contains": "Hello Ross"}     (optional substring check)
    """
    cmd = stage.get("command") or stage.get("shell_cmd")
    if not cmd:
        return ("ERROR: claude_verify stage missing 'command' or 'shell_cmd'", False)
    try:
        if isinstance(cmd, list):
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                               cwd=str(ROOT))
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=60, cwd=str(ROOT))
        exit_ok = r.returncode == stage.get("expect_exit", 0)
        text = ((r.stdout or "") + (("\n[stderr]\n"+r.stderr) if r.stderr else ""))[:2000]
        needle = stage.get("expect_contains")
        contains_ok = (needle is None) or (needle in text)
        passed = exit_ok and contains_ok
        verdict = (
            f"CLAUDE_VERIFY: exit={r.returncode} contains={needle!r}→{contains_ok} passed={passed}\n"
            f"---output---\n{text}"
        )
        return (verdict, passed)
    except subprocess.TimeoutExpired:
        return ("CLAUDE_VERIFY: timeout at 60s", False)
    except Exception as e:
        return (f"CLAUDE_VERIFY: exception {e}", False)


def progress(chain_id: str) -> dict:
    """Fire ONE stage of the chain — the current_stage."""
    chains = _load_chains()
    chain = _find_chain(chain_id, chains)
    if not chain: raise SystemExit(f"chain {chain_id!r} not found")
    if chain["status"] in ("complete", "verify_failed"):
        return {"skipped": True, "reason": f"terminal status: {chain['status']}"}
    idx = chain["current_stage"]
    if idx >= len(chain["stages"]):
        chain["status"] = "complete"
        chain["final_verdict"] = "all stages done"
        _save_chains(chains)
        return {"skipped": True, "reason": "all stages already done"}

    chain["status"] = "running"
    _save_chains(chains)

    stage = chain["stages"][idx]
    print(f"═ chain {chain_id!r} · stage {idx+1}/{len(chain['stages'])} · kind={stage['kind']}")

    # 2026-07-03: kind='claude_verify' bypasses Wren entirely — deterministic runner
    if stage["kind"] == "claude_verify":
        t0 = time.time()
        verdict, passed = _run_claude_verify(stage)
        wall = round(time.time() - t0, 2)
        stage.update({
            "done": True, "output": verdict, "ts": utc_iso(),
            "session_id": "claude_verify", "wall_s": wall,
            "verified_by": "claude_subprocess", "passed": passed,
        })
        chain["current_stage"] = idx + 1
        if not passed:
            chain["status"] = "verify_failed"
            chain["final_verdict"] = f"[stage {idx+1} claude_verify FAILED] " + verdict[:400]
            _save_chains(chains)
            print(f"  ✗ claude_verify FAILED — chain halted")
            return {"chain_id": chain_id, "stage": idx, "wall_s": wall,
                    "output": verdict[:400], "status": "verify_failed", "done": True}
        if chain["current_stage"] >= len(chain["stages"]):
            chain["status"] = "complete"
            chain["final_verdict"] = verdict[:600]
        else:
            chain["status"] = "pending"
        _save_chains(chains)
        print(f"  ✓ claude_verify passed  wall={wall}s")
        return {"chain_id": chain_id, "stage": idx, "wall_s": wall,
                "output": verdict[:400], "status": chain["status"],
                "done": chain["current_stage"] >= len(chain["stages"])}

    # Standard Wren-dispatch stage
    prompt = _build_stage_prompt(chain, idx)

    t0 = time.time()
    try:
        r = subprocess.run(
            ["python3", str(WREN_AGENT), "--task", prompt],
            capture_output=True, text=True, timeout=STAGE_TIMEOUT)
        out = (r.stdout or "").strip()
        parts = re.split(r"━{5,}", out)
        final = parts[-2].strip() if len(parts) >= 2 else out[-1200:]
    except subprocess.TimeoutExpired:
        final = f"(stage timed out at {STAGE_TIMEOUT}s)"
        out = ""
    except Exception as e:
        final = f"(stage error: {e})"
        out = ""
    wall = round(time.time() - t0, 2)

    # extract session_id from the header block
    sess = ""
    for line in out.splitlines() if 'out' in dir() else []:
        if "wsess_" in line:
            i = line.find("wsess_")
            sess = line[i:i+20].split()[0] if i >= 0 else ""
            break

    chain["stages"][idx].update({
        "done": True,
        "output": final,
        "ts": utc_iso(),
        "session_id": sess,
        "wall_s": wall,
    })
    chain["current_stage"] = idx + 1
    # if this was the last stage, complete
    if chain["current_stage"] >= len(chain["stages"]):
        chain["status"] = "complete"
        chain["final_verdict"] = final[:600]
    else:
        chain["status"] = "pending"  # ready for next stage
    _save_chains(chains)

    print(f"  wall={wall}s  output_head={final[:120]}")
    return {"chain_id": chain_id, "stage": idx, "wall_s": wall, "output": final[:400],
            "status": chain["status"], "done": chain["current_stage"] >= len(chain["stages"])}


def run_all(chain_id: str, sleep_between: int = 3) -> dict:
    """Progress the chain stage-by-stage until it's complete."""
    chains = _load_chains()
    chain = _find_chain(chain_id, chains)
    if not chain: raise SystemExit(f"chain {chain_id!r} not found")
    n = len(chain["stages"])
    while True:
        chains = _load_chains()
        chain = _find_chain(chain_id, chains)
        if chain["status"] == "complete" or chain["current_stage"] >= n:
            break
        res = progress(chain_id)
        if res.get("skipped"): break
        time.sleep(sleep_between)
    chains = _load_chains()
    chain = _find_chain(chain_id, chains)
    return {"chain_id": chain_id, "status": chain["status"], "stages_done": chain["current_stage"],
            "final_verdict": chain["final_verdict"]}


def cmd_status():
    chains = _load_chains()
    print(f"{len(chains)} chains in flight:")
    for c in chains[-8:]:
        n = len(c["stages"])
        done = sum(1 for s in c["stages"] if s.get("done"))
        print(f"  {c['id']:35}  {done}/{n} done  status={c.get('status','?')}  {c.get('title','')[:60]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-file", help="path to JSON spec file")
    ap.add_argument("--progress", help="fire the next stage of a chain")
    ap.add_argument("--run-all", help="progress a chain until complete")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--sleep", type=int, default=3)
    a = ap.parse_args()
    if a.status: cmd_status(); return
    if a.new_file:
        spec = json.load(open(a.new_file))
        c = new_chain(spec)
        print(json.dumps({"created": c["id"], "stages": len(c["stages"])}, indent=2))
        return
    if a.progress:
        r = progress(a.progress); print(json.dumps(r, indent=2)); return
    if a.run_all:
        r = run_all(a.run_all, sleep_between=a.sleep); print(json.dumps(r, indent=2)); return
    ap.print_help()


if __name__ == "__main__":
    main()
