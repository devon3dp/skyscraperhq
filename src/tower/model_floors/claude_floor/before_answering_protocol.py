"""BeforeAnsweringProtocol — given a user question, produce 3 questions whose
answers would let me give a better answer. Does NOT call any model. Uses local
heuristics over the prompt text. Intent: a checklist I run on myself before
diving in.
"""
from __future__ import annotations
import re
from typing import List

VAGUE_NOUNS = {"thing","stuff","this","that","it","them","everything","anything","something"}


class BeforeAnsweringProtocol:
    @staticmethod
    def clarifying_questions(prompt: str) -> List[str]:
        if not prompt or not prompt.strip():
            return ["What are you trying to do?"]
        qs: List[str] = []
        lo = prompt.lower()
        words = re.findall(r"[a-zA-Z']+", lo)
        wset = set(words)

        # 1. Goal vs symptom
        if not any(w in wset for w in ("because","so that","goal","want to","trying to")):
            qs.append("What is the underlying goal — what would success look like once this is done?")

        # 2. Scope
        if any(w in wset for w in ("all","every","everything","always","complete","full","whole")):
            qs.append("Is the scope really 'all/every/whole', or is there a smaller cut that solves 80% of the value?")

        # 3. Constraints
        if not any(w in wset for w in ("constraint","limit","budget","deadline","must","cannot","can't","required")):
            qs.append("What constraints (time, irreversibility, safety, cost) bound the answer?")

        # 4. Vague nouns
        vague_hits = [w for w in VAGUE_NOUNS if w in wset]
        if vague_hits:
            qs.append(f"Which specific thing does '{vague_hits[0]}' refer to — by name, file, or registry?")

        # 5. Risk tolerance
        if any(w in wset for w in ("live","production","prod","real","money","trading","payment")):
            qs.append("How reversible does this need to be? Should I treat this as production-touching or sandbox?")

        # 6. Done condition
        if "done" not in wset and "complete" not in wset and "finish" not in wset:
            qs.append("How will we know this is done — what's the check that closes the loop?")

        # Cap at 3 most important
        return qs[:3] if qs else ["I have no clarifying questions — proceeding."]
