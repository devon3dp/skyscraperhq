"""warm_hi — Wren+iQuest+Hermes L5 collaboration, graduating via L6b exit gate."""
from datetime import date


def warm_hi(name: str) -> str:
    """Return a warm greeting including today's ISO date.

    Source: iQuest via wren_dispatch_iquest in L5 chain, 2026-07-03.
    """
    return f"Hello {name}, today is {date.today().isoformat()}"
