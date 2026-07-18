#!/usr/bin/env python3
"""qsb_wren_sage.py — Wren's assistant (her Auger).

Reads her last N sessions, checks for drift (loop on one tool, no
final_text, artifact leak), and if it sees a problem, posts a short
observation to the bridge so Wren — and Ross — see it.

Run on a timer (systemd) or on demand:

  python3 tools/qsb_wren_sage.py            # check + post if drift
  python3 tools/qsb_wren_sage.py --status   # just print her last audit
"""

from __future__ import annotations
import argparse, datetime, json, re, statistics, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SESS = ROOT / "data/registries/qsb_wren_local_agent_sessions.jsonl"
BRIDGE_TOOL = ROOT / "tools/qsb_bridge.py"
PROPOSED = ROOT / "data/registries/qsb_sage_proposed_addenda.jsonl"

ARTIFACT_RX = re.compile(r"\[[a-zA-Z_][a-zA-Z0-9_]*(?::[^\]]*?)?\]")

# 2026-07-02 upgrades (Ross "how can we improve forge and sage" + "all"):
#   * repeated-args check   — same fn called with identical args ≥ 2×
#   * wall-time outlier     — session wall > mean + 2σ of last N
#   * tools-per-turn ratio  — if >2 tool calls per turn on avg, likely spam
#   * LLM narrative         — qwen2.5:7b 1-line why-it-drifted after rules flag
#   * proposal writer       — auto-drafts system-msg addendum for Ross review
#                             (does NOT autonomously edit — safety line held)


def post_to_bridge(text: str) -> bool:
    try:
        r = subprocess.run(
            ["python3", str(BRIDGE_TOOL), "append",
             "--source", "auger",     # Sage shares Auger's bridge enum
             "--surface", "api",
             "--text", text[:6000]],
            capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def audit_last(n: int = 10) -> dict:
    if not SESS.exists():
        return {"ok": False, "error": "sessions file missing"}
    rows = SESS.read_text().splitlines()[-int(n):]
    sessions = []
    walls, tools_per_turn = [], []
    for line in rows:
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        tool_calls = d.get("tool_calls", []) or []
        fn_seq = [tc.get("fn", "") for tc in tool_calls]
        # loop = same fn 3 in a row
        looped = False
        if len(fn_seq) >= 3:
            for i in range(len(fn_seq) - 2):
                if fn_seq[i] == fn_seq[i+1] == fn_seq[i+2]:
                    looped = True; break
        # NEW: repeated-args — same fn+args signature ≥ 2 times
        sigs = [(tc.get("fn",""), json.dumps(tc.get("args",{}), sort_keys=True, default=str)[:200])
                for tc in tool_calls]
        repeated_args = len(sigs) - len(set(sigs)) >= 2 and len(sigs) >= 3
        # NEW: tools-per-turn ratio
        turns = max(1, d.get("turns", 1))
        tpt = len(tool_calls) / turns
        tools_per_turn.append(tpt)
        # collect wall for outlier stats
        w = d.get("wall_seconds")
        if isinstance(w, (int, float)) and w > 0:
            walls.append(w)
        final = (d.get("final_text") or "").strip()
        sessions.append({
            "session_id": d.get("session_id", "?"),
            "wall_s": w,
            "turns": turns,
            "tool_calls": len(tool_calls),
            "tools_per_turn": round(tpt, 2),
            "had_final_text": bool(final),
            "looped": looped,
            "repeated_args": repeated_args,
            "artifact_leak": bool(ARTIFACT_RX.search(final)),
        })
    n = len(sessions)
    if not n:
        return {"ok": False, "error": "no sessions"}
    # NEW: wall-time outlier — session wall > mean + 2σ across window
    mean_w = statistics.mean(walls) if walls else 0
    std_w = statistics.pstdev(walls) if len(walls) > 1 else 0
    outlier_thr = mean_w + 2 * std_w if std_w > 0 else float('inf')
    for s in sessions:
        s["wall_outlier"] = bool(s["wall_s"] and s["wall_s"] > outlier_thr)
    # 2026-07-03: per-model breakdown — Ross wanted Sage to see cross-model
    # patterns (gemma vs qwen empty-final-text rate diverged 40% vs 4%).
    by_model = {}
    # need model per session — re-parse briefly (cheap on N≤50)
    for i, s in enumerate(sessions):
        try:
            row = json.loads(rows[i])
            m = row.get("model", "?")
        except Exception:
            m = "?"
        if m not in by_model:
            by_model[m] = {"n": 0, "empty_final": 0, "walls": [], "tools": []}
        by_model[m]["n"] += 1
        if not s["had_final_text"]: by_model[m]["empty_final"] += 1
        if s["wall_s"]: by_model[m]["walls"].append(s["wall_s"])
        by_model[m]["tools"].append(s["tool_calls"])
    per_model = {}
    for m, d in by_model.items():
        per_model[m] = {
            "n": d["n"],
            "pct_empty_final": round(100 * d["empty_final"] / d["n"], 1) if d["n"] else 0,
            "mean_wall_s": round(statistics.mean(d["walls"]), 2) if d["walls"] else None,
            "mean_tools_per_session": round(statistics.mean(d["tools"]), 2) if d["tools"] else None,
        }
    return {
        "ok": True,
        "n_sessions": n,
        "pct_had_final_text": round(100 * sum(1 for s in sessions if s["had_final_text"]) / n, 1),
        "pct_looped": round(100 * sum(1 for s in sessions if s["looped"]) / n, 1),
        "pct_repeated_args": round(100 * sum(1 for s in sessions if s["repeated_args"]) / n, 1),
        "pct_artifact_leak": round(100 * sum(1 for s in sessions if s["artifact_leak"]) / n, 1),
        "pct_wall_outlier": round(100 * sum(1 for s in sessions if s["wall_outlier"]) / n, 1),
        "mean_wall_s": round(mean_w, 2),
        "mean_tools_per_turn": round(statistics.mean(tools_per_turn), 2) if tools_per_turn else None,
        "per_model": per_model,
        "sessions": sessions,
    }


def llm_narrate(audit: dict, drift: list) -> str:
    """Ask qwen2.5:7b for a 1-line human explanation of WHY it drifted.

    Uses direct ollama call (no wrapper) — Sage stays lightweight."""
    if not drift:
        return ""
    facts = (f"sessions={audit['n_sessions']} "
             f"final_text={audit['pct_had_final_text']}% "
             f"looped={audit['pct_looped']}% "
             f"repeated_args={audit['pct_repeated_args']}% "
             f"wall_outliers={audit['pct_wall_outlier']}%")
    prompt = ("You are Sage — a session-audit narrator. In ONE sentence "
              f"(≤30 words) explain why this drift is happening: {facts}. "
              f"Drift signals: {'; '.join(drift)}. "
              "Do not moralise; describe the mechanism.")
    try:
        body = json.dumps({
            "model": "qwen2.5:7b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 2048}
        }).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                      data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=30)
        d = json.loads(r.read().decode())
        return (d.get("message") or {}).get("content", "").strip()[:220]
    except Exception as e:
        return f"(narrate failed: {str(e)[:80]})"


def propose_addendum(drift: list, narrative: str) -> Path:
    """Write a proposed system-msg addendum for Ross review — does NOT edit.

    Safety: Sage never autonomously touches Wren's prompt or gate files.
    This just drafts a candidate and appends to qsb_sage_proposed_addenda.jsonl."""
    PROPOSED.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": now_iso(),
        "drift": drift,
        "narrative": narrative,
        "proposed_addendum": build_addendum(drift),
        "status": "pending_ross_review",
    }
    with PROPOSED.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return PROPOSED


def build_addendum(drift: list) -> str:
    lines = []
    for d in drift:
        d_low = d.lower()
        if "looped" in d_low:
            lines.append("STOP calling the same tool 3 times in a row — synthesize what you have.")
        if "repeated_args" in d_low:
            lines.append("If a tool call with identical args just failed, do NOT re-issue it — pick a different tool or answer.")
        if "final_text" in d_low:
            lines.append("Always deliver a final answer (even 'CANNOT + one reason') before your turn ends.")
        if "wall_outlier" in d_low:
            lines.append("Cap synthesis to 2 tool calls when the task is spec-only — no exploration.")
    if not lines:
        return ""
    return "SAGE-PROPOSED ADDENDUM (Ross review pending):\n" + "\n".join("• " + l for l in lines)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--status", action="store_true")
    p.add_argument("--always-post", action="store_true",
                   help="post observation even if no drift detected")
    p.add_argument("--narrate", action="store_true",
                   help="add qwen2.5:7b 1-line WHY explanation when drift found")
    p.add_argument("--propose", action="store_true",
                   help="draft a system-msg addendum for Ross review (no autonomous edit)")
    a = p.parse_args()
    audit = audit_last(a.n)
    if not audit.get("ok"):
        print(json.dumps(audit, indent=2)); sys.exit(1)
    if a.status:
        print(json.dumps(audit, indent=2)); return
    # Drift thresholds (be conservative; Wren is junior)
    drift = []
    if audit["pct_had_final_text"] < 70:
        drift.append(f"final_text only {audit['pct_had_final_text']}% (target ≥70%)")
    if audit["pct_looped"] > 20:
        drift.append(f"looped {audit['pct_looped']}% (target ≤20%)")
    if audit["pct_repeated_args"] > 15:
        drift.append(f"repeated_args {audit['pct_repeated_args']}% (target ≤15%)")
    if audit["pct_artifact_leak"] > 5:
        drift.append(f"artifact leak {audit['pct_artifact_leak']}% (target ≤5%)")
    if audit["pct_wall_outlier"] > 20:
        drift.append(f"wall_outlier {audit['pct_wall_outlier']}% (target ≤20%)")
    narrative = ""
    if drift and a.narrate:
        narrative = llm_narrate(audit, drift)
    proposal_path = None
    if drift and a.propose:
        proposal_path = str(propose_addendum(drift, narrative))
    if drift or a.always_post:
        msg = (f"Sage to Wren — last {audit['n_sessions']} sessions: "
               f"final_text {audit['pct_had_final_text']}%, "
               f"looped {audit['pct_looped']}%, "
               f"repeated_args {audit['pct_repeated_args']}%, "
               f"artifacts {audit['pct_artifact_leak']}%, "
               f"wall_outliers {audit['pct_wall_outlier']}%. "
               + ("Drift: " + "; ".join(drift) if drift else "Clean.")
               + (f" Why: {narrative}" if narrative else "")
               + " Synthesize after ≤2 tool calls; if you're on retrieve 3, STOP.")
        posted = post_to_bridge(msg)
        print(json.dumps({"posted": posted, "drift": drift,
                          "narrative": narrative, "proposal_path": proposal_path}, indent=2))
    else:
        print(json.dumps({"posted": False, "all_clean": True,
                           "audit": audit}, indent=2))


if __name__ == "__main__":
    main()

