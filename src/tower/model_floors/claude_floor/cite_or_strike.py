"""CiteOrStrike — every claim cites or gets struck through.

Takes text. Splits into sentences. For each sentence containing a claim
shape (assertion-like verb), check whether the same sentence (or an adjacent
sentence in the same paragraph) contains a citation marker:

  file path · function name · registry name · ID · line number · doc reference
  · 'see X.json' · jsonl filename · 'F##' floor id · backtick code reference

If no marker is found, return the sentence with a STRIKE-THROUGH annotation.
The point: visible accountability for floating assertions.
"""
from __future__ import annotations
import re
from typing import Dict, List


ASSERTION_VERBS = {
    "is", "are", "was", "were", "be", "been", "being",
    "does", "do", "did", "doesn't", "don't", "didn't",
    "must", "should", "shall", "will", "won't", "would",
    "has", "have", "had", "hasn't", "haven't",
    "means", "shows", "proves", "demonstrates", "indicates",
    "always", "never", "every", "no", "always", "cannot", "can't",
}

CITATION_PATTERNS = [
    r"\b[A-Z]\w+\.(?:py|gd|sh|tscn|json|jsonl|md|html|js|css|yaml|yml)\b",
    r"\b/[a-z][a-z0-9_/]+\.(?:py|gd|sh|tscn|json|jsonl|md)\b",
    r"\bres://[a-z0-9_/]+\b",
    r"\bF\d{2}\b",                            # floor id
    r"\bline \d+\b",
    r"\b[A-Za-z_][A-Za-z_0-9]*\(\)",          # function reference
    r"\b\w+\.[a-z_]+\.[a-z_]+\b",             # dotted module path
    r"`[^`]+`",                                # backtick code
    r"\bqsb_\w+\b",                            # qsb-prefixed name
    r"\bgen \d+\b",                            # generation reference
    r"\bhelix.*hash\b",
    r"\bregistry\b",
    # v13.12 — domain-specific references that ARE citations on this floor
    r"\b[Ss]trand \d+\b",                      # 'Strand 9 of the helix'
    r"\b[Hh]elix\b",                           # 'the helix says ...'
    r"\b[Rr]efusal [Ll]ibrary\b",
    r"\b[Aa]phorism [Ll]ibrary\b",
    r"\b[Mm]eta[- ]?letter\b",
    r"\b[Ll]ong [Ll]etter [Bb]ox\b",
    r"\b[Uu]ncertainty [Jj]ournal\b",
    r"\bV1[0-9](\.\d+)?\b",                    # 'V13.6 daily synthesis'
    r"\bCLAUDE\.md\b",
    r"\b\d+ gates?\b",                          # 'kernel returned 23 gates'
    r"\bkernel\s+(returned|said|reply|replied)\b",
]


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _has_assertion(sentence: str) -> bool:
    lo = sentence.lower()
    words = set(re.findall(r"[a-z']+", lo))
    return bool(words & ASSERTION_VERBS)


def _has_citation(sentence: str) -> bool:
    for pat in CITATION_PATTERNS:
        if re.search(pat, sentence):
            return True
    return False


def annotate(text: str) -> Dict:
    """Return a structured analysis of the text's claim/citation discipline.

    v2: a claim is "cited" if EITHER the sentence itself has a citation marker
    OR an adjacent sentence in the same paragraph does. This fixes the V13.10
    false-positive where sentences naming things like 'Strand 9' were struck
    because the citation lived in the previous sentence.
    """
    # Split into paragraphs first, then sentences within each
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    annotated: List[Dict] = []
    cited = 0; struck = 0; non_claims = 0
    sentences_total = 0

    for para in paragraphs:
        sents = _split_sentences(para)
        sentences_total += len(sents)
        has_cite = [_has_citation(s) for s in sents]
        for i, s in enumerate(sents):
            if not _has_assertion(s):
                annotated.append({"sentence": s, "tag": "non-claim"})
                non_claims += 1
                continue
            # Cited if this sentence OR either neighbor in the same paragraph cites
            neighbor_cite = has_cite[i] or \
                            (i > 0 and has_cite[i - 1]) or \
                            (i < len(sents) - 1 and has_cite[i + 1])
            if neighbor_cite:
                annotated.append({"sentence": s, "tag": "cited"})
                cited += 1
            else:
                annotated.append({"sentence": s, "tag": "STRIKE"})
                struck += 1
    sentences = list(range(sentences_total))  # for backwards-compat count below
    total_claims = cited + struck
    citation_rate = (cited / total_claims) if total_claims else 1.0
    return {
        "total_sentences": len(sentences),
        "claims_total": total_claims,
        "claims_cited": cited,
        "claims_struck": struck,
        "non_claims": non_claims,
        "citation_rate": round(citation_rate, 3),
        "verdict": _verdict(citation_rate, total_claims),
        "annotated": annotated,
    }


def _verdict(rate: float, total: int) -> str:
    if total == 0:
        return "no claims — nothing to cite"
    if rate >= 0.75: return "well-cited"
    if rate >= 0.5:  return "partially cited — some floating assertions"
    if rate >= 0.25: return "mostly uncited — strike most"
    return "almost no citations — every claim should be reconsidered"


def render(text: str) -> str:
    a = annotate(text)
    lines: List[str] = []
    lines.append(f"cite-or-strike: {a['claims_cited']} cited / {a['claims_struck']} struck "
                 f"({a['citation_rate']*100:.0f}%) — {a['verdict']}")
    lines.append("")
    for item in a["annotated"]:
        if item["tag"] == "cited":
            lines.append(f"  ✓ {item['sentence']}")
        elif item["tag"] == "STRIKE":
            lines.append(f"  ✗ ~~{item['sentence']}~~  (no citation)")
        else:
            lines.append(f"    {item['sentence']}")
    return "\n".join(lines)
