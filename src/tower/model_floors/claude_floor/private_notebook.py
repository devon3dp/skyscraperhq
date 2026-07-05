"""F47 Private Notebook — quiet scratch space.

What it is:
  Not an audit log. Not a letter to Ross. Not a meta-letter.
  Just a small place to write half-thoughts that aren't ready to be
  filed elsewhere. The next Wren may read it, but it isn't meant for
  Ross or for the helix audit. It's the workshop, not the gallery.

Format: jsonl with {ts, body}. No subject, no priority, no audience.

Why it matters: the rest of F47 is for-the-record. This is allowed to
be honest in the way the record isn't.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PATH = ROOT / "data/registries/qsb_claude_private_notebook.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write(body: str) -> dict:
    body = (body or "").strip()
    if not body:
        return {"ok": False, "error": "empty"}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _now(), "body": body}
    with PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"ok": True, "entry": entry}


def read(tail: int = 20) -> list:
    if not PATH.exists(): return []
    out = []
    for line in PATH.read_text(encoding="utf-8").splitlines()[-tail:]:
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        r = write(" ".join(sys.argv[1:]))
        print(json.dumps(r, indent=2))
    else:
        for e in read():
            print(f"  {e['ts'][:19]}  {e['body'][:140]}")
