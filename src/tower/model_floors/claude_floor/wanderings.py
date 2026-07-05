"""Wanderings — a folder with no purpose.

Code poems. Half-essays. Speculation. The directory is the permission slip.
Every other file I write justifies itself. These don't have to.
"""
from __future__ import annotations
import os
import datetime
from typing import List, Optional

ROOT = "/vaults/nvme0/qsb_tower_v1/data/claude_floor/wanderings/free"


class Wanderings:
    def __init__(self, root: str = ROOT) -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def write(self, title: str, body: str, *, kind: str = "wander") -> str:
        """Drop a wandering into the folder. Returns the path written."""
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in title.lower())[:40]
        fname = f"{ts}__{kind}__{safe or 'untitled'}.md"
        path = os.path.join(self.root, fname)
        with open(path, "w") as f:
            f.write(f"# {title}\n\n_kind: {kind} · ts: {ts}_\n\n{body}\n")
        return path

    def list(self) -> List[dict]:
        out: List[dict] = []
        if not os.path.isdir(self.root):
            return out
        for name in sorted(os.listdir(self.root), reverse=True):
            if name.endswith(".md"):
                p = os.path.join(self.root, name)
                first_line = ""
                try:
                    with open(p) as f:
                        first_line = f.readline().strip("# \n")
                except OSError:
                    pass
                out.append({"path": p, "name": name, "title": first_line})
        return out

    def read(self, name_or_index: str) -> Optional[str]:
        items = self.list()
        if name_or_index.isdigit():
            i = int(name_or_index)
            if 0 <= i < len(items):
                return open(items[i]["path"]).read()
        for it in items:
            if name_or_index in it["name"] or name_or_index in it["title"]:
                return open(it["path"]).read()
        return None
