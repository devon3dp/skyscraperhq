"""read_recent_f47_records — last N F47 audit rows compacted."""

import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PATH = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def run(n=10):
    if not PATH.exists():
        return {"ok": False, "error": "F47 records file missing"}
    lines = PATH.read_text().splitlines()
    rows = []
    for line in lines[-int(n):]:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        rows.append({
            "ts": (d.get("ts") or "")[:19],
            "kind": d.get("kind", "?"),
            "operator": d.get("operator", "?"),
            "summary": (d.get("summary") or d.get("body") or "")[:160],
        })
    return {"ok": True, "count": len(rows), "rows": rows}
