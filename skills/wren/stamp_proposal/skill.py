"""stamp_proposal — Wren formally proposes something. Lands in F47 records."""

import datetime, json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def run(title="", body=""):
    if not title or not body:
        return {"ok": False, "error": "title + body required"}
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")
    row = {
        "ts": ts, "kind": "wren_proposal", "operator": "wren",
        "title": title[:200], "body": body[:1200],
        "awaiting": "claude_review_via_mutual_review",
    }
    with open(F47, "a") as f:
        f.write(json.dumps(row) + "\n")
    return {"ok": True, "ts": ts, "proposal_kind": "wren_proposal"}
