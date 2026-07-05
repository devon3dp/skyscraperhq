"""skill: write_session_diary_line — append one line to qsb_session_diary.md."""
import datetime, pathlib

DIARY = pathlib.Path("/vaults/nvme0/qsb_tower_v1/qsb_session_diary.md")


def run(text: str) -> dict:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    line = f"{ts[:19]}Z · Wren · {text[:240]}\n"
    with DIARY.open("a") as f:
        f.write(line)
    return {"ok": True, "line": line.strip()}
