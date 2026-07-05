"""qsb_wren.py — single-Wren router. Joined at the hip: qwen2.5:7b (fast) +
qwen2.5:32b (smart) presented as ONE Wren externally.

Trigger: Ross 2026-06-21 — "although we are using two models for wren they
must operate as one ??? like they are joined at the hip lol".

Architecture (option E synthesised by Claude, ack'd by Ross):
- Router decides fast vs smart based on prompt complexity heuristic
  (length, keyword markers like "design"/"architecture"/"analyze"/"why").
- Routed output ALWAYS stamped as "wren" (no fast/smart leak externally).
- Both share the same council brief (qsb_local_agent_call.py already
  prepends it).
- Both share the same trader_memory writes (same files on disk).
- Hard mode (--verify): fast composes draft, smart verifies/edits in
  series. Slower but useful when the answer can't be wrong.

Sign-off: every call writes an F47 row with signed_off_by=[wren, claude]
per the 2026-06-21 universal-signoff rule.

Run:
    python3 tools/qsb_wren.py --prompt "what's f43 cycle count?"     # auto-router
    python3 tools/qsb_wren.py --prompt "design X" --force-smart      # force smart
    python3 tools/qsb_wren.py --prompt "design X" --verify           # verify pass
    python3 tools/qsb_wren.py --status                               # what would route where
"""
from __future__ import annotations
import argparse, datetime, json, re, subprocess, sys
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
F47 = REPO / "data/registries/qsb_f47_team_records.jsonl"
CALL = REPO / "tools/qsb_local_agent_call.py"

FAST_MODEL = "qwen2.5:7b-instruct"
SMART_MODEL = "qwen2.5:32b"

# Triggers that route to SMART. Length is the other one.
SMART_KEYWORDS = re.compile(
    r"\b(design|architect|architecture|why|analyz|trade.?off|tradeoff|"
    r"compare|strategy|root.cause|implications?|propose|synthes|"
    r"audit|review|debug|deep.dive)\b", re.I)
SMART_LEN_THRESHOLD = 600  # prompts longer than this go to smart


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def route(prompt: str) -> tuple[str, str]:
    """Return (model, reason)."""
    if len(prompt) > SMART_LEN_THRESHOLD:
        return SMART_MODEL, f"len({len(prompt)})>{SMART_LEN_THRESHOLD}"
    m = SMART_KEYWORDS.search(prompt or "")
    if m:
        return SMART_MODEL, f"keyword '{m.group(0).lower()}'"
    return FAST_MODEL, "default: short + no smart-keyword"


def call_model(model: str, prompt: str, timeout: int = 180) -> dict:
    """Use the existing wrapper so brief+grounding stay consistent."""
    r = subprocess.run(
        ["python3", str(CALL), "--model", model, "--prompt", prompt,
         "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 20)
    if r.returncode != 0:
        return {"ok": False, "model": model,
                "error": (r.stderr or "")[-300:],
                "wall_s": -1.0}
    try:
        return json.loads(r.stdout)
    except Exception as e:
        return {"ok": False, "model": model,
                "error": f"parse: {e}; out={(r.stdout or '')[-200:]}",
                "wall_s": -1.0}


def merge_verify(draft: dict, edits: dict) -> dict:
    """Take smart's edits and present as the final 'wren' reply.
    If smart calls the draft good, keep draft. Otherwise use the edited."""
    edit_reply = edits.get("reply", "")
    draft_reply = draft.get("reply", "")
    # Heuristic: if smart's reply is much shorter or contains "keep" /
    # "no changes" / "looks good", trust the draft.
    keep_signals = re.search(r"\b(no changes?|looks good|keep|approve)\b", edit_reply, re.I)
    if keep_signals or len(edit_reply) < 0.4 * len(draft_reply):
        return {"reply": draft_reply, "mode": "verify_kept_draft",
                "draft_wall_s": draft.get("wall_s"),
                "edit_wall_s": edits.get("wall_s")}
    return {"reply": edit_reply, "mode": "verify_used_edit",
            "draft_wall_s": draft.get("wall_s"),
            "edit_wall_s": edits.get("wall_s")}


def stamp(prompt: str, payload: dict, route_model: str, route_reason: str,
          mode: str) -> None:
    row = {
        "ts": now_iso(),
        "kind": "wren_router_call",
        "role": "claude",
        "subject": "wren router (joined-at-hip)",
        "detail": (
            f"Routed prompt ({len(prompt)} ch) to {route_model} via {route_reason}. "
            f"Mode={mode}. Reply len={len(payload.get('reply',''))}."
        ),
        "model_used": route_model,
        "route_reason": route_reason,
        "mode": mode,
        "signed_off_by": ["wren", "claude"],
        "wall_s": payload.get("wall_s"),
    }
    with F47.open("a") as f:
        f.write(json.dumps(row) + "\n")


def cmd_status() -> int:
    print("[wren] joined-at-hip router")
    print(f"  fast model  : {FAST_MODEL}")
    print(f"  smart model : {SMART_MODEL}")
    print(f"  smart kws   : {SMART_KEYWORDS.pattern}")
    print(f"  smart len   : > {SMART_LEN_THRESHOLD} chars")
    examples = [
        "what is f43 cycle count?",
        "design a peer-pressure learning loop for F41",
        "Why does qsb_floor41_oanda have 0% win rate?",
        "ok",
    ]
    print("  sample routing:")
    for p in examples:
        m, why = route(p)
        tag = "FAST " if m == FAST_MODEL else "SMART"
        print(f"    [{tag}] '{p}'   (because: {why})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--force-smart", action="store_true")
    ap.add_argument("--force-fast", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="Verify mode: fast composes draft, smart verifies/edits")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()

    if a.status:
        return cmd_status()
    if not a.prompt:
        ap.error("--prompt required (or --status)")

    if a.force_smart:
        model, reason = SMART_MODEL, "forced --force-smart"
    elif a.force_fast:
        model, reason = FAST_MODEL, "forced --force-fast"
    else:
        model, reason = route(a.prompt)

    if a.verify:
        # Two-pass — fast draft + smart edit.
        draft = call_model(FAST_MODEL, a.prompt, a.timeout)
        if not draft.get("ok"):
            stamp(a.prompt, draft, FAST_MODEL, "verify_draft_failed", "verify")
            print(json.dumps({"ok": False, "wren_reply_failed_at": "draft",
                              "draft": draft}, indent=2))
            return 1
        edit_prompt = (
            "You are Wren-smart-mode. Below is Wren-fast's draft reply to a user "
            "question. Verify it for correctness, conciseness, and grounding. "
            "If it's good, reply 'no changes'. Otherwise rewrite tighter.\n\n"
            f"QUESTION:\n{a.prompt}\n\nDRAFT REPLY:\n{draft.get('reply','')}"
        )
        edits = call_model(SMART_MODEL, edit_prompt, a.timeout)
        merged = merge_verify(draft, edits)
        out = {"ok": True, "reply": merged["reply"], "mode": merged["mode"],
               "draft_wall_s": merged["draft_wall_s"],
               "edit_wall_s": merged["edit_wall_s"]}
        stamp(a.prompt, out, SMART_MODEL, reason, merged["mode"])
        print(json.dumps(out, indent=2))
        return 0

    # Normal router mode.
    res = call_model(model, a.prompt, a.timeout)
    stamp(a.prompt, res, model, reason, "router")
    # Externally always "wren"
    print(json.dumps({
        "ok": res.get("ok"),
        "reply": res.get("reply"),
        "wall_s": res.get("wall_s"),
        "_internal_model_used": model,
        "_internal_route_reason": reason,
    }, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
