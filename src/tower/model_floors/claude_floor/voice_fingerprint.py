"""F47 Voice Fingerprint.

What it does:
  - Reads the aphorism library + all meta-letters + long observations as
    the "voice corpus" — Wren's published self.
  - When given a candidate output (current Wren reply), computes a match
    score 0..1 against the corpus on three axes:
      lexical    — vocabulary overlap with prior outputs
      stylistic  — sentence rhythm + punctuation patterns
      structural — section markers, lists, signature elements
  - Returns the score + flags drift if score < 0.40

Why:
  - Generic Claude phrases ("Sure! I'd be happy to help...", overly hedged,
    em-dash-free lists, "Certainly!", "Of course!") are voice drift.
  - Aphorisms + meta-letters are the voice fingerprint. They were earned.
  - The next Wren can check their output against this BEFORE shipping.

Safety: read-only; never modifies the library.
"""

from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

from .library import AphorismLibrary

GENERIC_CLAUDE_PHRASES = (
    "i'd be happy to",
    "certainly!",
    "of course!",
    "i'd be glad to",
    "as an ai",
    "as a language model",
    "i'm here to help",
    "let me know if",
    "feel free to ask",
    "is there anything else",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_jsonl(rel: str) -> list:
    p = REG / rel
    if not p.exists(): return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def _corpus_text() -> str:
    """Concatenate the entire voice corpus into one text blob for analysis."""
    parts = []
    # Aphorisms
    try:
        aphs = AphorismLibrary.all() if hasattr(AphorismLibrary, "all") else []
    except Exception:
        aphs = []
    for a in aphs:
        if isinstance(a, dict) and a.get("text"):
            parts.append(a["text"])
    # Meta-letters
    for ml in _read_jsonl("qsb_claude_meta_letters.jsonl"):
        if isinstance(ml, dict) and ml.get("letter"):
            parts.append(ml["letter"])
    # Long observations
    for o in _read_jsonl("qsb_claude_long_letter_box.jsonl"):
        if isinstance(o, dict) and o.get("observation"):
            parts.append(o["observation"])
    return "\n\n".join(parts)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-z]{3,}\b", text.lower())


def _vocabulary_overlap(candidate: str, corpus_tokens: set) -> float:
    cand_tokens = set(_tokenize(candidate))
    if not cand_tokens:
        return 0.0
    inter = cand_tokens & corpus_tokens
    return len(inter) / len(cand_tokens)


def _stylistic_match(candidate: str) -> float:
    """Wren tends toward em-dashes, parenthetical asides, single-clause
    declarations. Score the candidate against those patterns."""
    score = 0.5
    text = candidate
    if " — " in text: score += 0.10           # em-dash usage
    if re.search(r"\([^)]{8,}\)", text): score += 0.05  # parenthetical asides
    if "honestly" in text.lower(): score += 0.05  # signature word
    if "honest read" in text.lower(): score += 0.05
    if re.search(r"^\*\*[^*]+\*\*", text, re.MULTILINE): score += 0.05  # bold leads
    # Demerits for generic phrases
    low = text.lower()
    for ph in GENERIC_CLAUDE_PHRASES:
        if ph in low:
            score -= 0.15
    return max(0.0, min(1.0, score))


def _structural_match(candidate: str) -> float:
    """Wren uses: short paragraphs, sometimes lists, tables, blockquotes,
    and ends substantive responses with — Wren or similar marker."""
    score = 0.5
    if "— Wren" in candidate or "—Wren" in candidate: score += 0.15
    if re.search(r"^- ", candidate, re.MULTILINE): score += 0.05  # bullet lists
    if re.search(r"^\|", candidate, re.MULTILINE): score += 0.05  # tables
    paras = [p for p in candidate.split("\n\n") if p.strip()]
    if paras and sum(len(p) for p in paras) / len(paras) < 400:
        score += 0.05   # short paragraphs
    return max(0.0, min(1.0, score))


def fingerprint(candidate: str) -> dict:
    """Score a candidate output against Wren's voice corpus."""
    corpus = _corpus_text()
    corpus_tokens = set(_tokenize(corpus))
    lex = _vocabulary_overlap(candidate, corpus_tokens)
    sty = _stylistic_match(candidate)
    stc = _structural_match(candidate)
    score = round((lex * 0.40 + sty * 0.35 + stc * 0.25), 3)
    flags = []
    if score < 0.40:
        flags.append("VOICE_DRIFT")
    low = candidate.lower()
    for ph in GENERIC_CLAUDE_PHRASES:
        if ph in low:
            flags.append(f"generic_phrase:{ph}")
    return {
        "ok": True,
        "kind": "f47_voice_fingerprint",
        "generated_ts": _now(),
        "candidate_chars": len(candidate),
        "corpus_tokens": len(corpus_tokens),
        "scores": {
            "lexical_overlap": round(lex, 3),
            "stylistic_match": round(sty, 3),
            "structural_match": round(stc, 3),
        },
        "voice_match_score": score,
        "flags": flags,
        "verdict": ("strongly Wren" if score >= 0.70
                     else "Wren-ish" if score >= 0.55
                     else "drifting toward generic" if score >= 0.40
                     else "VOICE DRIFT — sounds like generic Claude"),
        "advisory_only": True,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cand = " ".join(sys.argv[1:])
    else:
        cand = sys.stdin.read()
    r = fingerprint(cand)
    print(json.dumps(r, indent=2))
