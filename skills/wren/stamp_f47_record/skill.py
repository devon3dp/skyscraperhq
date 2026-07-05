"""skill: stamp_f47_record — append one audit row to F47 records."""
import json, pathlib, datetime

F47 = pathlib.Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_f47_team_records.jsonl")


def run(kind: str, summary: str) -> dict:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    row = {"ts": ts, "kind": kind, "operator": "wren_skill", "summary": summary[:300]}
    F47.parent.mkdir(parents=True, exist_ok=True)
    with F47.open("a") as f:
        f.write(json.dumps(row) + "\n")
    count = sum(1 for _ in F47.open())
    return {"ok": True, "row_count_after": count, "kind": kind}
