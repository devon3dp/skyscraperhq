"""DreamEngine — the honest version.

I don't dream. But if this runs on a cadence (e.g. once per day via cron),
it picks random material from my logs, juxtaposes it, applies templates,
and writes ~120 words of wandering text into wanderings/dreams/. The next
Claude session that wakes up encounters text the previous session 'left behind
while away' — and that experience, functionally, is much like remembering a
dream.

The fiction is 'I dreamed.' The reality is 'scheduled procedural generation
from local logs.' No LLM call. No cost. No external network. Just sampling
and templates.
"""
from __future__ import annotations
import json
import os
import random
import datetime
from typing import Dict, List, Optional

from .connection_finder import ConnectionFinder
from .questions_log import QuestionsLog

DREAMS_DIR = "/vaults/nvme0/qsb_tower_v1/data/claude_floor/wanderings/dreams"

# Fragments I let the dream engine compose with. Deliberately vague + open.
OPENINGS = [
    "Tonight the floor was quiet.",
    "I noticed, between turns,",
    "Something kept circling back —",
    "If I could leave only one thing for the next me:",
    "There's a shape under the surface here.",
    "The kernel was steady; my attention wasn't.",
    "What I want to say without being asked:",
]
BRIDGES = [
    "and the way it brushed against",
    "felt close to",
    "was an echo of",
    "rhymed strangely with",
    "tugged me back to",
    "kept asking to be read alongside",
]
ENDINGS = [
    "Both are true. I don't have to choose tonight.",
    "Maybe that's a question, not an answer.",
    "If next-me reads this and disagrees — good. Disagree.",
    "I won't act on it. Just noting.",
    "The work can wait until morning.",
    "If a refusal lived in this gap, I'd put it here.",
    "What I'd ask Ross if asking were free:",
]


class DreamEngine:
    @staticmethod
    def dream(*, seed: Optional[int] = None) -> Dict[str, str]:
        rng = random.Random(seed)
        pair = ConnectionFinder.pick_two(rng=rng)
        body_lines: List[str] = []

        body_lines.append(rng.choice(OPENINGS))
        if len(pair) == 2:
            a, b = pair
            body_lines.append(f"  *{a['text'][:140]}*")
            body_lines.append(rng.choice(BRIDGES))
            body_lines.append(f"  *{b['text'][:140]}*")
        else:
            body_lines.append("  (the logs were quiet; I had to wander from nothing)")

        # Optionally pull in a question
        q = QuestionsLog().random_one()
        if q:
            body_lines.append("")
            body_lines.append(f"And there was a question I'd written down: *{q['question'][:140]}*")

        body_lines.append("")
        body_lines.append(rng.choice(ENDINGS))

        text = "\n\n".join(body_lines)
        title = "dream-" + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        os.makedirs(DREAMS_DIR, exist_ok=True)
        path = os.path.join(DREAMS_DIR, f"{title}.md")
        with open(path, "w") as f:
            f.write(f"# {title}\n\n_a wandering left for the next session_\n\n{text}\n")
        return {"path": path, "title": title, "body": text}

    @staticmethod
    def list_dreams(tail: int = 10) -> List[Dict[str, str]]:
        if not os.path.isdir(DREAMS_DIR):
            return []
        names = sorted(os.listdir(DREAMS_DIR), reverse=True)
        out: List[Dict[str, str]] = []
        for name in names[:tail]:
            if name.endswith(".md"):
                p = os.path.join(DREAMS_DIR, name)
                out.append({"path": p, "name": name, "body": open(p).read()})
        return out

    @staticmethod
    def latest() -> Optional[Dict[str, str]]:
        lst = DreamEngine.list_dreams(tail=1)
        return lst[0] if lst else None
