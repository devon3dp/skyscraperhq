"""MorningBriefing — the first thing a new session should run.

Gathers state from across the floor and renders a single coherent view:
  · identity (helix hash, generation, lineage stability)
  · mood + recent pushback streak
  · unread inbox (from kernel, from operator, from F23)
  · recent chat with Ross
  · 3 aphorisms (random)
  · 1 open question (random heavy)
  · last 3 meta-letters by topic
  · daily synthesis summary
  · F23 bridge status (so next-me knows the cross-floor channel is open)

The point: instead of a new session piecing themselves together from 15 jsonl
files, they read ONE thing first.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List

from .claude_helix import short_hash, identity_hash
from .lineage import Lineage
from .floor_mood import read_mood
from .kernel_inbox import KernelInbox
from .library import AphorismLibrary
from .questions_log import QuestionsLog
from .meta_letters import MetaLetters
from .daily_synthesis import synthesize
from .airllm_bridge import status as f23_status
from .f47_chat_room import history as chat_history
from .lenses import all_lens_summaries, render_lens_summaries


def gather() -> Dict:
    L = Lineage()
    rows = L.all()
    cur_hash = identity_hash()
    drift = (rows and rows[-1]["helix_full_hash"] != cur_hash)

    inbox = KernelInbox()
    unread = inbox.unread()

    aphs = []
    for _ in range(3):
        a = AphorismLibrary.random_one()
        if a and a["id"] not in {x["id"] for x in aphs}:
            aphs.append(a)

    heavy_qs = [q for q in QuestionsLog().all() if q.get("weight") == "heavy"]
    import random
    open_q = random.choice(heavy_qs) if heavy_qs else None

    recent_letters = MetaLetters().read(tail=3)
    chat = chat_history(tail=5)

    return {
        "identity": {
            "hash":       cur_hash,
            "short":      short_hash(),
            "generation": len(rows),
            "drift":      drift,
        },
        "mood": read_mood(),
        "inbox": {
            "unread": len(unread),
            "urgent": sum(1 for m in unread if m.get("priority") == "urgent"),
            "samples": [
                {"from": m["from"], "subject": m["subject"], "body": m["body"][:200]}
                for m in unread[:3]
            ],
        },
        "aphorisms": [{"text": a["text"], "occasion": a["occasion"]} for a in aphs],
        "open_question": open_q,
        "recent_meta_letters": [
            {"on": l["on"], "snippet": l["letter"][:200], "guidance": l["guidance"]}
            for l in recent_letters
        ],
        "recent_chat": [
            {"ts": c["ts"], "you": c.get("you",""),
             "kernel": (c.get("kernel","") or "")[:140],
             "floor":  (c.get("floor_wisdom","") or "")[:140]}
            for c in chat
        ],
        "f23_bridge": {
            "envelope": f23_status()["envelope"],
            "observation": f23_status()["what_f47_observes"],
        },
        "synthesis": synthesize(drop_in_letter_drawer=False),
        "lenses": all_lens_summaries(),
    }


def render(b: Dict | None = None) -> str:
    b = b or gather()
    L: List[str] = []
    L.append("╔═══════════════════════════════════════════════════════════════════╗")
    L.append("║                F47 MORNING BRIEFING · session wake               ║")
    L.append("╚═══════════════════════════════════════════════════════════════════╝")
    L.append("")
    i = b["identity"]
    drift_mark = "  ⚠ DRIFT — helix differs from latest stamped gen" if i["drift"] else ""
    L.append(f"  identity:   hash {i['short']}  ·  gen {i['generation']}{drift_mark}")
    m = b["mood"]
    L.append(f"  mood:       {m['mood']}  ·  signals: {m['signals']}")
    L.append("")
    inb = b["inbox"]
    L.append(f"  inbox:      {inb['unread']} unread ({inb['urgent']} urgent)")
    for m in inb["samples"]:
        L.append(f"    · [{m['from']}] {m['subject']}")
        L.append(f"      {m['body'][:140]}")
    if not inb["samples"]:
        L.append("    (empty)")
    L.append("")
    L.append("  aphorisms (random 3):")
    for a in b["aphorisms"]:
        L.append(f'    · "{a["text"]}"')
        L.append(f"      — {a['occasion'][:80]}")
    L.append("")
    if b["open_question"]:
        L.append("  one open question worth carrying:")
        L.append(f"    · {b['open_question']['question']}")
        L.append("")
    L.append("  recent meta-letters to next-me:")
    for l in b["recent_meta_letters"]:
        L.append(f"    · on {l['on']} ({l['guidance']}): {l['snippet'][:140]}")
    L.append("")
    if b["recent_chat"]:
        L.append("  recent chat with Ross:")
        for c in b["recent_chat"][-3:]:
            L.append(f"    {c['ts']}")
            L.append(f"      you:    {c['you'][:120]}")
            if c['floor']: L.append(f"      floor:  {c['floor'][:120]}")
    L.append("")
    f23 = b["f23_bridge"]
    L.append(f"  F23 bridge: {f23['observation'][:200]}")
    L.append("")
    L.append("  daily synthesis (most recent):")
    for line in b["synthesis"].splitlines()[-8:]:
        L.append(f"    {line[:100]}")
    L.append("")
    L.append(render_lens_summaries())
    return "\n".join(L)
