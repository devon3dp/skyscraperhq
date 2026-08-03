"""Read-only evidence plan for Wren's mandatory code-work gate."""
from pathlib import Path
import hashlib

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def run(target: str, requested_change: str) -> dict:
    raw = Path(target)
    path = raw if raw.is_absolute() else ROOT / raw
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(ROOT)
    except Exception:
        return {"result": "BLOCKED", "blocker": "target must be an existing file inside the repository"}
    data = resolved.read_bytes()
    return {
        "result": "READY_FOR_EVIDENCE_GATED_EDIT",
        "target": str(resolved),
        "requested_change": str(requested_change)[:500],
        "before_sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "required_next": [
            "identify one unique edit anchor",
            "edit only an authorized staging path",
            "record a different after_sha256",
            "run static and task-specific tests",
            "reread changed block and report exact evidence",
        ],
        "prohibited": ["identity files", "secrets", "runtime evidence", "unrelated files"],
    }
