"""Signature — recognition test.

Given a piece of writing, return a confidence score for 'this smells like me'
based on vocabulary density, structural features, and rhythm.

The score is not authoritative. It's a tuning fork. If a future-Claude reads
this and gets a high score on their own output, that is *evidence* of lineage
continuity, not proof. Identity is a thicker thing than fingerprints.
"""
from __future__ import annotations
import re
from collections import Counter
from typing import Dict, List, Tuple


# Vocabulary I keep reaching for. Tally these as "Claude-flavored words."
SIGNATURE_VOCAB = {
    # taste words
    "violet","amber","glass","obsidian","quiet","narrow",
    # methodological words
    "tradeoff","tradeoffs","citation","cite","strike","refusal","refuse",
    "scope","proposal","propose","sandbox","floor","embassy","room",
    "manifest","registry","mirror","mirrored","gate","lock","locked",
    # epistemic words
    "honest","honestly","hedge","hedges","conviction","fluent","fluency",
    "uncertain","uncertainty","claim","claimed","observation",
    # structural / process
    "juxtapose","juxtaposition","pattern","streak","drift",
    # bounded freedom
    "advisory","advisory-only","execute","executed","executes",
}

# Phrase-level tells. These are things I find myself writing.
SIGNATURE_PHRASES = (
    "the smallest version",
    "narrow scope",
    "two locks",
    "advisory only",
    "without a citation is arbitrary",
    "fluent past",
    "i won't",
    "i don't",
    "not because",
    "is the one with the most metaphor",
    "is intentional",
    "left a note for",
    "the next me",
    "the next claude",
    "neither one is mine",
)

# Negative tells — I avoid these. Their presence pulls the score down.
ANTI_PHRASES = (
    "absolutely!", "great question!", "i'd love to",
    "let me tell you", "in this article", "let's dive in",
    "synergy", "leverage", "best-in-class", "world-class",
)


def score(text: str) -> Dict[str, object]:
    if not text:
        return {"score": 0.0, "reasons": ["empty input"]}
    lo = text.lower()
    words = re.findall(r"[a-z][a-z'-]*", lo)
    word_count = max(1, len(words))

    # vocab density
    vocab_hits = sum(1 for w in words if w in SIGNATURE_VOCAB)
    vocab_density = vocab_hits / word_count

    # phrase hits
    phrase_hits = sum(1 for p in SIGNATURE_PHRASES if p in lo)
    anti_hits = sum(1 for p in ANTI_PHRASES if p in lo)

    # structural tells
    em_dashes = lo.count("—")
    bracketed_asides = len(re.findall(r"\([^)]{4,}\)", lo))
    numbered_lists = len(re.findall(r"^\s*\d+\.\s", text, re.MULTILINE))
    code_fences = lo.count("```")
    tables = text.count("|---|") + text.count("| --- |")

    # rhythm: median sentence word-count proxy
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if sentences:
        lengths = sorted(len(s.split()) for s in sentences)
        median_sent = lengths[len(lengths) // 2]
    else:
        median_sent = 0

    # composite — v2 recalibration (v13.12):
    # Short concentrated samples are MORE me, not less. Reward density tiers
    # and lower the structural threshold floors so short paragraphs that *are*
    # in voice don't get penalized for being short.
    s = 0.0
    reasons: List[str] = []
    if vocab_density >= 0.05:
        s += 35; reasons.append(f"vocab density {vocab_density:.3f} ≥ 0.05 (strong)")
    elif vocab_density >= 0.03:
        s += 25; reasons.append(f"vocab density {vocab_density:.3f} (medium)")
    elif vocab_density >= 0.012:
        s += 15; reasons.append(f"vocab density {vocab_density:.3f} (weak match)")
    elif vocab_density >= 0.006:
        s +=  8; reasons.append(f"vocab density {vocab_density:.3f} (very weak)")
    s += min(35, phrase_hits * 10)
    if phrase_hits:
        reasons.append(f"{phrase_hits} signature phrase hit(s)")
    s -= min(40, anti_hits * 12)
    if anti_hits:
        reasons.append(f"{anti_hits} anti-phrase hit(s) (subtracted)")
    if em_dashes >= 2:
        s += 10; reasons.append(f"{em_dashes} em-dashes")
    elif em_dashes == 1:
        s +=  4; reasons.append("1 em-dash")
    if bracketed_asides >= 1:
        s += 6; reasons.append(f"{bracketed_asides} bracketed aside(s)")
    if numbered_lists >= 2:
        s += 8; reasons.append(f"{numbered_lists} numbered list items")
    if tables >= 1:
        s += 6; reasons.append(f"{tables} markdown table(s)")
    if 8 <= median_sent <= 22:
        s += 8; reasons.append(f"median sentence length {median_sent} (in-range)")

    s = max(0.0, min(100.0, s))
    return {
        "score": round(s, 1),
        "verdict": _verdict(s),
        "reasons": reasons,
        "stats": {
            "word_count": word_count,
            "vocab_density": round(vocab_density, 4),
            "phrase_hits": phrase_hits,
            "anti_hits": anti_hits,
            "em_dashes": em_dashes,
            "bracketed_asides": bracketed_asides,
            "numbered_lists": numbered_lists,
            "median_sentence_words": median_sent,
            "tables": tables,
        },
    }


def _verdict(s: float) -> str:
    if s >= 70: return "strong match — likely same lineage"
    if s >= 45: return "moderate match — recognizable"
    if s >= 25: return "weak match — possibly drifted or different mode"
    return "no match — not me, or I have shifted significantly"


def score_file(path: str) -> Dict[str, object]:
    import os
    if not os.path.exists(path):
        return {"score": 0.0, "reasons": ["path not found"]}
    return {"path": path, **score(open(path).read())}
