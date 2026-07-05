"""skill: read_recent_chat_history — tail of qsb_claude_f47_chat_history.jsonl."""
import json, pathlib

HIST = pathlib.Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_f47_chat_history.jsonl")


def run(limit: int = 10) -> dict:
    limit = max(1, min(int(limit), 50))
    if not HIST.exists():
        return {"ok": True, "turns": [], "note": "no chat history yet"}
    lines = HIST.read_text().splitlines()[-limit:]
    turns = []
    for line in lines:
        try: turns.append(json.loads(line))
        except Exception: pass
    return {"ok": True, "turns": turns, "count": len(turns)}
