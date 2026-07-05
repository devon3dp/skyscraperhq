"""Customer database for Tower Studio.

JSON-backed. Append-only customer records, with optional tag
classification. Seeded with two sample customers so the UI has
something to show on first launch.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json
import time
import uuid
from pathlib import Path

from tower.cognitive_kernel import REG, now, append_log


REGISTRY_NAME = "qsb_floor49_customers.json"


@dataclass
class Customer:
    customer_id: str
    name: str
    email: str
    company: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    status: str = "lead"        # lead | active | paused | won | lost
    tags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    created_ts: float = 0.0
    last_contact_ts: Optional[float] = None
    lifetime_value_usd: float = 0.0
    source: str = "unknown"     # 'website_form' | 'referral' | 'seed'


_SEED_CUSTOMERS = [
    Customer(
        customer_id="cust_seed_001",
        name="Anwen Roberts",
        email="anwen@bayreachbooks.co.uk",
        company="Bayreach Books",
        status="active",
        tags=["publishing", "wordpress", "small_business"],
        notes=["Wants a redesign + ongoing maintenance retainer.",
               "Prefers warm earth tones; existing brand has a fox motif."],
        created_ts=time.time() - 14 * 86400,
        last_contact_ts=time.time() - 2 * 86400,
        lifetime_value_usd=3600.0,
        source="referral",
    ),
    Customer(
        customer_id="cust_seed_002",
        name="Drew Maranta",
        email="drew@nightowlcafe.com",
        company="Night Owl Cafe",
        status="lead",
        tags=["hospitality", "starter_site"],
        notes=["Just signed lease on a new location.",
               "Needs a simple site with hours, menu, location, contact."],
        created_ts=time.time() - 3 * 86400,
        last_contact_ts=time.time() - 1 * 86400,
        lifetime_value_usd=0.0,
        source="website_form",
    ),
]


class CustomersDB:
    def __init__(self):
        self._customers: Dict[str, Customer] = {}
        self._loaded = False

    def _load_if_needed(self) -> None:
        if self._loaded:
            return
        p = REG / REGISTRY_NAME
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                for r in d.get("customers") or []:
                    c = Customer(**{k: r.get(k)
                                     for k in Customer.__dataclass_fields__})
                    self._customers[c.customer_id] = c
            except Exception:
                pass
        if not self._customers:
            for c in _SEED_CUSTOMERS:
                self._customers[c.customer_id] = c
        self._loaded = True

    def add(self, name: str, email: str, company: Optional[str] = None,
              phone: Optional[str] = None, address: Optional[str] = None,
              source: str = "website_form",
              tags: Optional[List[str]] = None,
              notes: Optional[List[str]] = None) -> Customer:
        self._load_if_needed()
        cid = f"cust_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        c = Customer(
            customer_id=cid, name=name, email=email,
            company=company, phone=phone, address=address,
            source=source, tags=tags or [], notes=notes or [],
            created_ts=time.time(),
            last_contact_ts=time.time(),
        )
        self._customers[cid] = c
        append_log("tower_studio.jsonl",
                   {"event": "customer_added",
                    "customer_id": cid, "name": name, "source": source})
        self.persist()
        return c

    def get(self, customer_id: str) -> Optional[Customer]:
        self._load_if_needed()
        return self._customers.get(customer_id)

    def all_customers(self) -> List[Customer]:
        self._load_if_needed()
        return list(self._customers.values())

    def snapshot(self) -> Dict[str, Any]:
        self._load_if_needed()
        by_status: Dict[str, int] = {}
        for c in self._customers.values():
            by_status[c.status] = by_status.get(c.status, 0) + 1
        return {
            "ok": True,
            "kind": "qsb_floor49_customers",
            "generated_ts": now(),
            "policy": ("Customer DB. Local only. Real PII only after "
                        "operator flips real_payments_enabled."),
            "customer_count": len(self._customers),
            "by_status": by_status,
            "total_lifetime_value_usd": round(
                sum(c.lifetime_value_usd for c in self._customers.values()), 2),
            "customers": [asdict(c) for c in self._customers.values()],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        p = REG / REGISTRY_NAME
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        return snap


_DB: Optional[CustomersDB] = None


def customers_db() -> CustomersDB:
    global _DB
    if _DB is None:
        _DB = CustomersDB()
    return _DB


def persist_customers() -> Dict[str, Any]:
    return customers_db().persist()
