from pathlib import Path
from datetime import datetime, timezone
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_load_json_helper_fix_{ts}")
text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")

print("Backup:", backup)

helper = '''
def load_json(rel_path, fallback=None):
    """Read JSON relative to tower root. Dashboard-safe: never raises."""
    import json
    from pathlib import Path

    if fallback is None:
        fallback = {}

    try:
        path = ROOT / rel_path
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": str(exc),
            "path": str(rel_path),
        }

'''

if "def load_json(" in text:
    print("load_json already exists; no helper inserted.")
else:
    # Prefer placing helper after ROOT assignment.
    lines = text.splitlines(True)
    insert_at = None

    for i, line in enumerate(lines):
        if line.strip().startswith("ROOT ="):
            insert_at = i + 1
            break

    if insert_at is None:
        # Fallback: after imports.
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1

    lines.insert(insert_at, "\n" + helper)
    text = "".join(lines)
    SERVER.write_text(text, encoding="utf-8")
    print("Inserted dashboard-safe load_json helper.")

py_compile.compile(str(SERVER), doraise=True)
print("server.py compiles cleanly.")
