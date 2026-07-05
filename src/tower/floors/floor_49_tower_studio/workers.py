"""Tower Studio worker roster — designers, devs, copywriters.

Each worker has a role, a level (apprentice / journeyman / lead), and
optional certifications. Workers are conceptual; no external API calls.
The compensation engine pays them in QBC when projects complete.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time

from tower.cognitive_kernel import REG, now
import json


REGISTRY_NAME = "qsb_floor49_workers.json"


STUDIO_CURRICULUM: List[Dict[str, str]] = [
    {"id": "ws_01_html_css_fundamentals",
     "title": "HTML & CSS fundamentals",
     "audience": "frontend_developer",
     "summary": "Semantic HTML, modern CSS (grid, flex, custom props), accessibility basics."},
    {"id": "ws_02_design_systems",
     "title": "Design systems & brand consistency",
     "audience": "graphics_designer",
     "summary": "Tokens (colour, type, spacing), component thinking, brand kits."},
    {"id": "ws_03_copy_that_converts",
     "title": "Copy that converts",
     "audience": "copywriter",
     "summary": "Headline frameworks, social proof placement, calls to action."},
    {"id": "ws_04_python_backend_basics",
     "title": "Python backend basics",
     "audience": "backend_developer",
     "summary": "HTTP servers, JSON, form handling, env-var configuration."},
    {"id": "ws_05_pm_scoping",
     "title": "Project scoping & client comms",
     "audience": "project_manager",
     "summary": "Brief → scope → estimate → milestone gates → delivery."},
    {"id": "ws_06_qa_review_checklist",
     "title": "QA review checklist",
     "audience": "qa_reviewer",
     "summary": "Accessibility, copy proofing, link integrity, mobile probe."},
    {"id": "ws_07_client_success_followup",
     "title": "Client success & follow-up",
     "audience": "client_success_lead",
     "summary": "Day-7 check-in, day-30 health, renewal conversation."},
]


@dataclass
class StudioWorker:
    worker_id: str
    role: str
    level: str               # apprentice | journeyman | lead | principal
    name: str
    certifications: List[str] = field(default_factory=list)
    hire_ts: float = 0.0
    notes: List[str] = field(default_factory=list)


SEEDED_ROSTER: List[StudioWorker] = [
    StudioWorker("worker_designer_01", "graphics_designer", "journeyman",
                  "Ines Halloran", certifications=["ws_02_design_systems"],
                  hire_ts=time.time() - 30*86400),
    StudioWorker("worker_designer_02", "principal_designer", "principal",
                  "Wren Adekunle", certifications=["ws_02_design_systems",
                                                     "ws_05_pm_scoping"],
                  hire_ts=time.time() - 120*86400),
    StudioWorker("worker_frontend_01", "frontend_developer", "journeyman",
                  "Theo Marchetti", certifications=["ws_01_html_css_fundamentals"],
                  hire_ts=time.time() - 28*86400),
    StudioWorker("worker_frontend_02", "frontend_developer", "apprentice",
                  "Ade Nwosu", certifications=[],
                  hire_ts=time.time() - 6*86400),
    StudioWorker("worker_backend_01", "backend_developer", "lead",
                  "Lior Kahane", certifications=["ws_04_python_backend_basics"],
                  hire_ts=time.time() - 60*86400),
    StudioWorker("worker_copywriter_01", "copywriter", "journeyman",
                  "Mira Quint", certifications=["ws_03_copy_that_converts"],
                  hire_ts=time.time() - 22*86400),
    StudioWorker("worker_copywriter_02", "copywriter", "apprentice",
                  "Sami Routledge", certifications=[],
                  hire_ts=time.time() - 4*86400),
    StudioWorker("worker_pm_01", "project_manager", "lead",
                  "Devon Aalst", certifications=["ws_05_pm_scoping"],
                  hire_ts=time.time() - 90*86400),
    StudioWorker("worker_qa_01", "qa_reviewer", "journeyman",
                  "Robin Caldecott", certifications=["ws_06_qa_review_checklist"],
                  hire_ts=time.time() - 18*86400),
    StudioWorker("worker_csl_01", "client_success_lead", "journeyman",
                  "Imani Brevard", certifications=["ws_07_client_success_followup"],
                  hire_ts=time.time() - 45*86400),
]


def workers_snapshot() -> Dict[str, Any]:
    by_role: Dict[str, int] = {}
    by_level: Dict[str, int] = {}
    for w in SEEDED_ROSTER:
        by_role[w.role] = by_role.get(w.role, 0) + 1
        by_level[w.level] = by_level.get(w.level, 0) + 1
    return {
        "ok": True,
        "kind": "qsb_floor49_workers",
        "generated_ts": now(),
        "policy": ("Studio worker roster. Conceptual workers. "
                    "Compensation engine pays in QBC on project complete."),
        "worker_count": len(SEEDED_ROSTER),
        "by_role": by_role,
        "by_level": by_level,
        "curriculum_lesson_count": len(STUDIO_CURRICULUM),
        "curriculum": STUDIO_CURRICULUM,
        "workers": [asdict(w) for w in SEEDED_ROSTER],
    }


def persist_workers() -> Dict[str, Any]:
    snap = workers_snapshot()
    p = REG / REGISTRY_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap
