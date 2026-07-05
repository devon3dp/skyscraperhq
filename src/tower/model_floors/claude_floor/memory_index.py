"""F47 Memory Index — searchable index across F47's records.

What it does:
  - Indexes every meta-letter + long observation + letter-drawer note +
    kernel-inbox message + aphorism + question into a single searchable
    structure.
  - Supports query by keyword (lowercased substring).
  - Returns hits ranked by recency + match strength.
  - Letting future Wren ask: "what did past Wren say about X?"

Why:
  - The chain is already chronological. But chronological isn't the same as
    searchable. If gen 30 needs to know what gen 5 said about helix continuity,
    scrolling 200 entries is bad UX.

Returns:
  {
    query: "...",
    hit_count: int,
    hits: [
      {kind, ts, source_file, text_head, match_score},
      ...
    ]
  }

Safety: read-only.
"""

from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


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


def _index_all() -> list[dict]:
    """Aggregate every F47 record source into one normalized list."""
    items = []
    # Meta-letters
    for r in _read_jsonl("qsb_claude_meta_letters.jsonl"):
        if isinstance(r, dict):
            items.append({
                "kind": "meta_letter",
                "ts": r.get("ts", ""),
                "source": "qsb_claude_meta_letters.jsonl",
                "title": r.get("on") or r.get("topic", "(meta letter)"),
                "text": (r.get("letter") or "") + " " + (r.get("guidance") or ""),
            })
    # Long observations
    for r in _read_jsonl("qsb_claude_long_letter_box.jsonl"):
        if isinstance(r, dict):
            items.append({
                "kind": "observation",
                "ts": r.get("ts", ""),
                "source": "qsb_claude_long_letter_box.jsonl",
                "title": (r.get("observation") or "")[:60],
                "text": r.get("observation") or "",
            })
    # Letter drawer notes
    for r in _read_jsonl("qsb_claude_letter_drawer.jsonl"):
        if isinstance(r, dict):
            items.append({
                "kind": "letter_to_ross",
                "ts": r.get("ts", ""),
                "source": "qsb_claude_letter_drawer.jsonl",
                "title": (r.get("note") or "")[:60],
                "text": r.get("note") or "",
            })
    # Kernel inbox
    for r in _read_jsonl("qsb_claude_kernel_inbox.jsonl"):
        if isinstance(r, dict):
            items.append({
                "kind": "inbox_message",
                "ts": r.get("ts", ""),
                "source": "qsb_claude_kernel_inbox.jsonl",
                "title": r.get("subject", "")[:60],
                "text": (r.get("subject", "") + " " + (r.get("body") or "")),
            })
    # Aphorism library
    aph_path = REG / "qsb_claude_aphorism_library.json"
    if aph_path.exists():
        try:
            d = json.loads(aph_path.read_text(encoding="utf-8"))
            for a in d.get("aphorisms", d.get("entries", [])):
                if isinstance(a, dict):
                    items.append({
                        "kind": "aphorism",
                        "ts": a.get("ts", ""),
                        "source": "qsb_claude_aphorism_library.json",
                        "title": a.get("occasion", "(aphorism)"),
                        "text": a.get("text") or "",
                    })
        except Exception: pass
    # Questions log
    q_path = REG / "qsb_claude_questions_log.json"
    if q_path.exists():
        try:
            d = json.loads(q_path.read_text(encoding="utf-8"))
            for q in d.get("questions", d.get("entries", [])):
                if isinstance(q, dict):
                    items.append({
                        "kind": "open_question",
                        "ts": q.get("ts", ""),
                        "source": "qsb_claude_questions_log.json",
                        "title": q.get("question", "(open question)")[:60],
                        "text": q.get("question") or "",
                    })
        except Exception: pass
    return items


def search(query: str, limit: int = 12) -> dict:
    """Search the index. Case-insensitive substring match; multi-word ranks by
    how many terms hit. Recency tiebreaker."""
    q = (query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "empty query", "hits": []}
    terms = [t for t in re.split(r"\s+", q) if t]
    items = _index_all()
    scored = []
    for it in items:
        text_low = (it.get("text", "") + " " + it.get("title", "")).lower()
        hit_terms = [t for t in terms if t in text_low]
        if not hit_terms:
            continue
        scored.append({
            **it,
            "match_score": len(hit_terms) / max(1, len(terms)),
            "matched_terms": hit_terms,
        })
    # Rank: match_score desc, ts desc
    scored.sort(key=lambda x: (-x["match_score"], x.get("ts", "")), reverse=False)
    scored.sort(key=lambda x: (-x["match_score"], -ord(x.get("ts","2000")[0]) if x.get("ts") else 0))
    # Simpler: just sort by (-score, -ts string)
    scored.sort(key=lambda x: (-x["match_score"], x.get("ts", "")), reverse=True)
    scored.sort(key=lambda x: -x["match_score"])
    return {
        "ok": True,
        "kind": "f47_memory_search",
        "query": query,
        "terms": terms,
        "hit_count": len(scored),
        "hits": [
            {
                "kind": h["kind"],
                "ts": h.get("ts", ""),
                "source": h["source"],
                "title": h["title"],
                "text_head": h["text"][:240],
                "match_score": round(h["match_score"], 3),
                "matched_terms": h["matched_terms"],
            }
            for h in scored[:limit]
        ],
        "generated_ts": _now(),
        "advisory_only": True,
    }


def summary() -> dict:
    """Aggregate counts of the index."""
    items = _index_all()
    from collections import Counter
    by_kind = Counter(it["kind"] for it in items)
    return {
        "ok": True,
        "kind": "f47_memory_index_summary",
        "generated_ts": _now(),
        "total_entries": len(items),
        "by_kind": dict(by_kind),
        "advisory_only": True,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        r = search(q)
        print(json.dumps(r, indent=2)[:2000])
    else:
        s = summary()
        print(json.dumps(s, indent=2))
