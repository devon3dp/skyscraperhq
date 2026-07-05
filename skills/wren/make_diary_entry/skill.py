"""make_diary_entry — append a one-line entry to the session diary."""

import datetime
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
DIARY = ROOT / "qsb_session_diary.md"


def run(text=""):
    if not text or not text.strip():
        return {"ok": False, "error": "text required"}
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    line = f"{ts}  wren-diary: {text.strip()[:400]}\n"
    with open(DIARY, "a") as f:
        f.write(line)
    return {"ok": True, "appended": line.rstrip()}
