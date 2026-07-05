"""Floor 49 — Tower Studio (Web Design + IT Services).

A real internal company. Customer DB, project pipeline, services catalog,
pricing in USD (advisory) and QBC (internal). Workers are simulated;
all execution gates remain locked.
"""

from .state import (
    FLAGS, floor_state_snapshot, persist_floor_state, tick,
)
from .customers import (
    Customer, customers_db, persist_customers,
)
from .services import (
    SERVICES_CATALOG, services_snapshot, quote_for,
)
from .projects import (
    Project, projects_db, persist_projects,
)

__all__ = [
    "FLAGS", "floor_state_snapshot", "persist_floor_state", "tick",
    "Customer", "customers_db", "persist_customers",
    "SERVICES_CATALOG", "services_snapshot", "quote_for",
    "Project", "projects_db", "persist_projects",
]
