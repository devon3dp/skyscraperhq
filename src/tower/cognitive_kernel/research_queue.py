"""ResearchQueue — Safe substitute for unrestricted internet access.

The IT floor (Tower Studio) and the Kernel itself can BOTH file
research questions. The Kernel never fetches anything on its own.
A SEPARATE Claude phase (called "research servicing") picks up
items from the queue, uses approved-tool WebFetch with an allowlist,
and writes the answer back into the queue.

Allowlist policy (queried by the servicing phase, not enforced here):
  · whitelisted domains live in `cognitive_research_allowlist.json`
  · the servicing phase refuses any URL not on the allowlist
  · each fetched page is logged with URL + bytes + timestamp

Items have states:
  open  → claimed_by_phase  → answered  → operator_reviewed
                            → blocked_by_allowlist
                            → fetch_failed

This keeps the IT floor genuinely useful for research without giving
the cognitive layer any network access of its own.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json
import time
import uuid

from . import write_registry, append_log, load, COG_REG, now


@dataclass
class ResearchItem:
    item_id: str
    question: str
    purpose: str                       # 'tower_studio_brief' | 'kernel_curiosity' | 'operator_request'
    requested_by: str                  # worker_id, 'kernel', or 'operator'
    requested_ts: float
    target_urls: List[str] = field(default_factory=list)  # hints; servicing phase still allowlists
    status: str = "open"               # see states above
    answer_summary: Optional[str] = None
    fetched_urls: List[str] = field(default_factory=list)
    fetched_bytes: int = 0
    answered_ts: Optional[float] = None
    notes: List[str] = field(default_factory=list)


# Allowlist seeds. Servicing phase enforces these.
DEFAULT_ALLOWLIST = [
    {"domain": "en.wikipedia.org",
     "rationale": "neutral reference",
     "categories": ["reference"]},
    {"domain": "developer.mozilla.org",
     "rationale": "web standards",
     "categories": ["web_dev"]},
    {"domain": "docs.python.org",
     "rationale": "language docs",
     "categories": ["python"]},
    {"domain": "developer.squareup.com",
     "rationale": "Square API reference (for the integration phase)",
     "categories": ["square"]},
    {"domain": "developer.oanda.com",
     "rationale": "OANDA API docs (practice only)",
     "categories": ["oanda"]},
    {"domain": "binance.com",
     "rationale": "Binance API docs (testnet only)",
     "categories": ["binance"]},
    {"domain": "openbanking.org.uk",
     "rationale": "UK Open Banking standard",
     "categories": ["halifax", "open_banking"]},
    {"domain": "unsplash.com",
     "rationale": "free image source — for catalog enrichment",
     "categories": ["images"]},
    {"domain": "pexels.com",
     "rationale": "free image source",
     "categories": ["images"]},
    {"domain": "pixabay.com",
     "rationale": "free image source",
     "categories": ["images"]},
    {"domain": "nasa.gov",
     "rationale": "public domain image source",
     "categories": ["images"]},
]


class ResearchQueue:

    def __init__(self):
        self._items: Dict[str, ResearchItem] = {}

    def file(self, question: str, purpose: str,
              requested_by: str,
              target_urls: Optional[List[str]] = None) -> ResearchItem:
        iid = f"r_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        item = ResearchItem(
            item_id=iid, question=question, purpose=purpose,
            requested_by=requested_by, requested_ts=time.time(),
            target_urls=list(target_urls or []),
        )
        self._items[iid] = item
        append_log("research_queue.jsonl", {
            "event": "filed", "item_id": iid,
            "question": question[:140], "requested_by": requested_by,
        })
        return item

    def claim(self, item_id: str, phase_label: str) -> bool:
        item = self._items.get(item_id)
        if not item or item.status != "open":
            return False
        item.status = "claimed_by_phase"
        item.notes.append(f"claimed by phase {phase_label}")
        append_log("research_queue.jsonl",
                   {"event": "claimed", "item_id": item_id,
                    "phase": phase_label})
        return True

    def answer(self, item_id: str, summary: str,
                 fetched_urls: List[str], fetched_bytes: int = 0) -> bool:
        item = self._items.get(item_id)
        if not item or item.status not in ("claimed_by_phase", "open"):
            return False
        item.answer_summary = summary
        item.fetched_urls = list(fetched_urls)
        item.fetched_bytes = fetched_bytes
        item.status = "answered"
        item.answered_ts = time.time()
        append_log("research_queue.jsonl", {
            "event": "answered", "item_id": item_id,
            "fetched_url_count": len(fetched_urls),
            "fetched_bytes": fetched_bytes,
        })
        return True

    def block(self, item_id: str, reason: str) -> bool:
        item = self._items.get(item_id)
        if not item:
            return False
        item.status = "blocked_by_allowlist"
        item.notes.append(reason)
        return True

    def operator_review(self, item_id: str, note: str = "") -> bool:
        item = self._items.get(item_id)
        if not item or item.status != "answered":
            return False
        item.status = "operator_reviewed"
        if note: item.notes.append(note)
        return True

    def open_items(self) -> List[ResearchItem]:
        return [i for i in self._items.values() if i.status == "open"]

    def snapshot(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for i in self._items.values():
            by_status[i.status] = by_status.get(i.status, 0) + 1
        return {
            "ok": True,
            "kind": "cognitive_research_queue",
            "generated_ts": now(),
            "policy": ("Kernel files research questions. Kernel does "
                        "NOT fetch. A separate phase services this queue "
                        "with allowlisted WebFetch."),
            "item_count": len(self._items),
            "by_status": by_status,
            "items": [asdict(i) for i in self._items.values()],
            "allowlist_default": DEFAULT_ALLOWLIST,
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_research_queue.json", snap)
        # Allowlist registry — read by the servicing phase
        write_registry("cognitive_research_allowlist.json", {
            "ok": True,
            "kind": "cognitive_research_allowlist",
            "generated_ts": now(),
            "policy": ("Servicing phase MUST NOT fetch any domain "
                        "outside this allowlist."),
            "allowlist": DEFAULT_ALLOWLIST,
        })
        return snap

    def load_from_snapshot(self) -> int:
        d = load(COG_REG / "cognitive_research_queue.json")
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("items") or []:
            iid = r.get("item_id")
            if not iid or iid in self._items:
                continue
            self._items[iid] = ResearchItem(
                item_id=iid,
                question=r.get("question", ""),
                purpose=r.get("purpose", ""),
                requested_by=r.get("requested_by", ""),
                requested_ts=float(r.get("requested_ts") or 0),
                target_urls=list(r.get("target_urls") or []),
                status=r.get("status", "open"),
                answer_summary=r.get("answer_summary"),
                fetched_urls=list(r.get("fetched_urls") or []),
                fetched_bytes=int(r.get("fetched_bytes") or 0),
                answered_ts=(float(r["answered_ts"]) if r.get("answered_ts") else None),
                notes=list(r.get("notes") or []),
            )
            count += 1
        return count


_RQ: Optional[ResearchQueue] = None


def research_queue() -> ResearchQueue:
    global _RQ
    if _RQ is None:
        _RQ = ResearchQueue()
    return _RQ
