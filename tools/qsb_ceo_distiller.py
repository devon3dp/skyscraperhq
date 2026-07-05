#!/usr/bin/env python3
"""qsb_ceo_distiller.py — turn TP + Acer + Wren + HQ recent thoughts into
persistent lessons WITHOUT touching their base system prompt.

Ross 2026-07-05: "i need them to learn and evolve ...period" + earlier
"stop fucking with there minds" = learning must happen OUTSIDE the base
prompt. Base prompt stays LOCKED. Lessons accrue in a sibling file.

Design:
  · Runs periodically (or on-demand) per CEO
  · Reads their mind file (mind_tp.json / mind_acer.json / qsb_wren_mind.json)
  · Extracts recent outbound thoughts (their own voice) + self-prompts
  · Distills repeat patterns into 1-line "lessons"
  · Appends to data/registries/lessons_<ceo>.jsonl (append-only, versioned)
  · HQ's /message calls prepend top-N lessons as per-turn context

The distillation itself uses the brain router (Groq is fastest + free)
so we don't need Claude tokens for this.

USAGE:
  python3 tools/qsb_ceo_distiller.py tp_pip
  python3 tools/qsb_ceo_distiller.py acer_cass
  python3 tools/qsb_ceo_distiller.py all
  python3 tools/qsb_ceo_distiller.py tp_pip --tail 6      # show recent lessons
"""
from __future__ import annotations
import argparse, json, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
sys.path.insert(0, str(ROOT / "tools"))

# Mind file locations
MIND = {
    "tp_pip":    "http://192.168.1.74:9110/state",  # fetch via /state (mind isn't local to HQ)
    "acer_cass": "http://192.168.1.78:9000/state",
    "wren":      REG / "qsb_wren_mind.json",
    "hq_claude": None,  # HQ uses self-prompt log
}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _fetch_state_thoughts(url: str) -> list[dict]:
    try:
        r = urllib.request.urlopen(url, timeout=6)
        d = json.loads(r.read())
        return d.get("recent_thoughts", []) or []
    except Exception:
        return []


def _read_local_mind_thoughts(p: Path) -> list[dict]:
    if not p.exists(): return []
    try:
        m = json.loads(p.read_text())
        return m.get("recent_thoughts", []) or []
    except Exception:
        return []


def _read_hq_self_prompts() -> list[dict]:
    p = REG / "qsb_hq_self_prompts.jsonl"
    if not p.exists(): return []
    out = []
    for line in p.read_text().splitlines()[-30:]:
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def gather_thoughts(ceo: str) -> list[str]:
    """Return a list of thought text strings for distillation."""
    if ceo in ("tp_pip", "acer_cass"):
        thoughts = _fetch_state_thoughts(MIND[ceo])
        # Prefer outbound (their own voice) + self_prompt (their reflections)
        return [t.get("text","") for t in thoughts
                if t.get("kind") in ("outbound","self_prompt") and t.get("text")]
    if ceo == "wren":
        thoughts = _read_local_mind_thoughts(MIND["wren"])
        return [t.get("text","") for t in thoughts if t.get("text")]
    if ceo == "hq_claude":
        sp = _read_hq_self_prompts()
        return [f"{s.get('question','')} → {s.get('next_move','')}" for s in sp
                if s.get("question")]
    return []


def distill_via_router(ceo: str, thoughts: list[str]) -> list[str]:
    """Use the brain router (Groq/DeepSeek/etc) to extract lessons."""
    if not thoughts:
        return []
    joined = "\n".join(f"- {t[:220]}" for t in thoughts[-20:])
    prompt = (
        f"You are extracting durable LESSONS from {ceo}'s recent thoughts. "
        f"A lesson is a short repeatable rule of thumb this CEO can apply "
        f"in future work. Ignore one-off events.\n\n"
        f"THOUGHTS:\n{joined}\n\n"
        f"Output ONLY a JSON array of 3-6 short lesson strings. Each lesson "
        f"is one sentence, <100 chars, actionable. No preamble. Example format:\n"
        f'["Always verify remote endpoints before quoting status", "..."]'
    )
    try:
        from qsb_brain_router import route
        reply, meta = route(prompt, task="reason", tier="worker",
                            caller=f"distiller_{ceo}")
        # Try to parse JSON out of reply
        import re
        m = re.search(r"\[.*\]", reply, re.DOTALL)
        if not m:
            return []
        arr = json.loads(m.group(0))
        return [str(x).strip() for x in arr if isinstance(x, str)][:6]
    except Exception as e:
        print(f"  ~ router failed: {e}", file=sys.stderr)
        return []


def append_lessons(ceo: str, lessons: list[str]) -> Path:
    path = REG / f"lessons_{ceo}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for l in lessons:
            f.write(json.dumps({"ts": _utc(), "ceo": ceo, "lesson": l}) + "\n")
    return path


def read_top_lessons(ceo: str, n: int = 6) -> list[str]:
    """For HQ to prepend into /message calls."""
    path = REG / f"lessons_{ceo}.jsonl"
    if not path.exists(): return []
    rows = []
    for line in path.read_text().splitlines()[-n*3:]:
        try:
            d = json.loads(line)
            l = d.get("lesson","").strip()
            if l and l not in rows: rows.append(l)
        except Exception: pass
    return rows[-n:]


def distill_one(ceo: str) -> dict:
    thoughts = gather_thoughts(ceo)
    if not thoughts:
        return {"ceo": ceo, "status": "no thoughts to distill"}
    lessons = distill_via_router(ceo, thoughts)
    if not lessons:
        return {"ceo": ceo, "status": "no lessons extracted",
                "thoughts_seen": len(thoughts)}
    p = append_lessons(ceo, lessons)
    return {"ceo": ceo, "status": "ok",
            "thoughts_seen": len(thoughts),
            "lessons_added": lessons,
            "written_to": str(p)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ceo", help="tp_pip · acer_cass · wren · hq_claude · all")
    ap.add_argument("--tail", type=int, default=0,
                    help="just print last N lessons for this CEO + exit")
    a = ap.parse_args()

    if a.tail > 0:
        for l in read_top_lessons(a.ceo, a.tail):
            print(f"  · {l}")
        return

    targets = list(MIND.keys()) if a.ceo == "all" else [a.ceo]
    for t in targets:
        r = distill_one(t)
        print(f"\n  {t}: {r.get('status')} · seen={r.get('thoughts_seen',0)}")
        for l in r.get("lessons_added",[]):
            print(f"    · {l}")


if __name__ == "__main__":
    main()
