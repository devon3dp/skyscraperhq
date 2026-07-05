"""KernelInbox — async messages from the Kernel (F55) addressed to Claude (F47).

The consult_kernel script is request-response. This is the inverse: the
Kernel (or anyone with write access to the inbox file, including the operator)
leaves messages here, and Claude reads them on next wakeup.

Read-only from Claude's side. Local-only.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import Dict, List, Optional

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_kernel_inbox.jsonl"


class KernelInbox:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def post(self, *, from_who: str = "Kernel (F55)", subject: str = "",
             body: str = "", priority: str = "normal") -> Dict:
        """Append a message TO Claude. Use sparingly. priority: low | normal | urgent."""
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "from": from_who,
            "to": "Claude (F47)",
            "subject": subject.strip(),
            "body": body.strip(),
            "priority": priority,
            "read": False,
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def all(self) -> List[Dict]:
        if not os.path.exists(self.path):
            return []
        return [json.loads(l) for l in open(self.path).read().splitlines() if l.strip()]

    def unread(self) -> List[Dict]:
        return [m for m in self.all() if not m.get("read")]

    def mark_all_read(self) -> int:
        msgs = self.all()
        n = 0
        for m in msgs:
            if not m.get("read"):
                m["read"] = True; n += 1
        with open(self.path, "w") as f:
            for m in msgs:
                f.write(json.dumps(m) + "\n")
        return n

    def summary(self) -> Dict:
        msgs = self.all()
        return {
            "total":  len(msgs),
            "unread": sum(1 for m in msgs if not m.get("read")),
            "urgent_unread": sum(1 for m in msgs if not m.get("read") and m.get("priority") == "urgent"),
        }
