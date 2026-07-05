from pathlib import Path
from datetime import datetime, UTC
import json

ROOT = Path("/vaults/nvme0/qsb_skyscraper")
IDENTITY_FILE = ROOT / "kernel" / "identity.json"

DEFAULT_IDENTITY = {
    "name": "QSB Kernel",
    "full_name": "Quantum Symbolic Brain Kernel",
    "version": "4.6-offline-kernel-symbolic",
    "role": "Locked Penthouse Kernel",
    "principle": "Models are workers. QSB is the kernel.",
    "architecture": "Penthouse kernel above floors, lifts, departments, and local model workers.",
    "created_or_verified": None
}

class IdentityCore:
    def __init__(self):
        IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not IDENTITY_FILE.exists():
            data = dict(DEFAULT_IDENTITY)
            data["created_or_verified"] = datetime.now(UTC).isoformat()
            IDENTITY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def status(self):
        return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
