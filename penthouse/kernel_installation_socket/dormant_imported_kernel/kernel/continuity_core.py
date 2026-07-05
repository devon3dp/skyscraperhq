from pathlib import Path
from datetime import datetime, UTC
import json
import hashlib

ROOT = Path("/vaults/nvme0/qsb_skyscraper")
STATE_FILE = ROOT / "kernel" / "continuity_state.json"

class ContinuityCore:
    def __init__(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, path):
        p = ROOT / path
        if not p.exists():
            return "missing"
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def boot_check(self):
        current = {
            "ts": datetime.now(UTC).isoformat(),
            "identity_hash": self._hash_file("kernel/identity.json"),
            "constitution_hash": self._hash_file("config/constitution.md"),
            "symbolic_hash": self._hash_file("kernel/symbolic_core.py"),
            "penthouse_hash": self._hash_file("executive/penthouse.py"),
            "memory_db_exists": (ROOT / "memory" / "qsb_memory.sqlite").exists(),
            "knowledge_db_exists": (ROOT / "knowledge" / "qsb_knowledge.sqlite").exists(),
            "mission_db_exists": (ROOT / "missions" / "qsb_missions.sqlite").exists(),
            "lift_db_exists": (ROOT / "bus" / "qsb_lifts.sqlite").exists()
        }

        previous = None
        status = "FIRST_KERNEL_BOOT"

        if STATE_FILE.exists():
            previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            drift = []
            for key in ["identity_hash", "constitution_hash", "symbolic_hash"]:
                if previous.get(key) != current.get(key):
                    drift.append(key)
            status = "CONTINUITY_CONFIRMED" if not drift else "CONTROLLED_KERNEL_DRIFT"
            current["drift"] = drift

        current["status"] = status
        current["previous"] = previous
        STATE_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current
