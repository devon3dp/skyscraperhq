"""Project pipeline for Tower Studio.

Each project: customer + service SKU + status + assigned workers + due
date + deliverables checklist.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json
import time
import uuid

from tower.cognitive_kernel import REG, now, append_log


REGISTRY_NAME = "qsb_floor49_projects.json"


@dataclass
class Project:
    project_id: str
    customer_id: str
    sku: str
    name: str
    status: str = "lead"        # lead | proposal_sent | in_progress | review | delivered | invoiced | paid | declined
    assigned_workers: List[str] = field(default_factory=list)
    deliverables_done: List[str] = field(default_factory=list)
    deliverables_pending: List[str] = field(default_factory=list)
    quoted_price_usd: float = 0.0
    invoiced_amount_usd: float = 0.0
    started_ts: float = 0.0
    due_ts: Optional[float] = None
    notes: List[str] = field(default_factory=list)


class ProjectsDB:
    def __init__(self):
        self._projects: Dict[str, Project] = {}
        self._loaded = False

    def _load_if_needed(self) -> None:
        if self._loaded:
            return
        p = REG / REGISTRY_NAME
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                for r in d.get("projects") or []:
                    pr = Project(**{k: r.get(k)
                                     for k in Project.__dataclass_fields__})
                    self._projects[pr.project_id] = pr
            except Exception:
                pass
        if not self._projects:
            # Seed a sample project so the pipeline view has something
            from .services import SERVICES_CATALOG
            seed = SERVICES_CATALOG[0]
            self._projects["proj_seed_001"] = Project(
                project_id="proj_seed_001",
                customer_id="cust_seed_001",
                sku=seed.sku, name=seed.name,
                status="in_progress",
                assigned_workers=["worker_designer_01",
                                    "worker_frontend_01",
                                    "worker_copywriter_01"],
                deliverables_done=["wireframe approved",
                                     "hero illustration draft"],
                deliverables_pending=["hero illustration final",
                                       "copy revision pass",
                                       "deploy-ready bundle"],
                quoted_price_usd=seed.price_usd,
                started_ts=time.time() - 4 * 86400,
                due_ts=time.time() + 1 * 86400,
                notes=["Customer prefers warm earth tones."],
            )
        self._loaded = True

    def create(self, customer_id: str, sku: str, name: str,
                quoted_price_usd: float,
                deliverables_pending: List[str],
                due_ts: Optional[float] = None) -> Project:
        self._load_if_needed()
        pid = f"proj_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        pr = Project(
            project_id=pid, customer_id=customer_id, sku=sku, name=name,
            status="proposal_sent", quoted_price_usd=quoted_price_usd,
            deliverables_pending=deliverables_pending,
            started_ts=time.time(), due_ts=due_ts,
        )
        self._projects[pid] = pr
        append_log("tower_studio.jsonl",
                   {"event": "project_created",
                    "project_id": pid, "customer_id": customer_id,
                    "sku": sku})
        self.persist()
        return pr

    def mark(self, project_id: str, status: str, note: str = "") -> bool:
        self._load_if_needed()
        pr = self._projects.get(project_id)
        if not pr:
            return False
        pr.status = status
        if note: pr.notes.append(note)
        append_log("tower_studio.jsonl",
                   {"event": "project_status",
                    "project_id": project_id, "status": status})
        self.persist()
        return True

    def all_projects(self) -> List[Project]:
        self._load_if_needed()
        return list(self._projects.values())

    def snapshot(self) -> Dict[str, Any]:
        self._load_if_needed()
        by_status: Dict[str, int] = {}
        for pr in self._projects.values():
            by_status[pr.status] = by_status.get(pr.status, 0) + 1
        return {
            "ok": True,
            "kind": "qsb_floor49_projects",
            "generated_ts": now(),
            "policy": ("Project pipeline. Advisory. No automatic billing. "
                        "Real invoicing requires operator gate flip."),
            "project_count": len(self._projects),
            "by_status": by_status,
            "total_quoted_usd": round(
                sum(p.quoted_price_usd for p in self._projects.values()), 2),
            "total_invoiced_usd": round(
                sum(p.invoiced_amount_usd for p in self._projects.values()), 2),
            "projects": [asdict(p) for p in self._projects.values()],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        p = REG / REGISTRY_NAME
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        return snap


_DB: Optional[ProjectsDB] = None


def projects_db() -> ProjectsDB:
    global _DB
    if _DB is None:
        _DB = ProjectsDB()
    return _DB


def persist_projects() -> Dict[str, Any]:
    return projects_db().persist()
