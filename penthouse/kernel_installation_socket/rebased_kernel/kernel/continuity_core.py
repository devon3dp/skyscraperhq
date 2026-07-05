# QSB Tower V1.3 — Rebased Kernel Package
# REBASE CHANGES:
#   1. ROOT rebased to KERNEL_STATE_ROOT under tower penthouse socket
#   2. _hash_file now resolves paths relative to this file's package directory
#   3. boot_check hash targets updated to rebased kernel file names
#   4. DB existence checks remapped to tower data/db paths
#   5. boot_check no longer nests the FULL prior record under "previous".
#      The earlier shape stored "previous" = entire prior state including
#      its own "previous", producing an unbounded chain that grew by one
#      level on every boot. That eventually exceeded Python's json.dumps
#      recursion limit (~1000) and surfaced through QSBKernelCore.__init__
#      as a RecursionError. Now we store only a flat summary of the prior
#      boot — drift detection is unchanged.
from pathlib import Path
from datetime import datetime, UTC
import json
import hashlib

KERNEL_STATE_ROOT = Path(
    "/vaults/nvme0/qsb_tower_v1/penthouse/kernel_installation_socket/rebased_kernel/state"
)
TOWER_DB_ROOT = Path("/vaults/nvme0/qsb_tower_v1/data/db")

# Directory containing this file — used for hashing rebased kernel source files
KERNEL_PACKAGE_DIR = Path(__file__).resolve().parent

STATE_FILE = KERNEL_STATE_ROOT / "continuity_state.json"

# Fields that travel into the "previous" summary. Anything else (in
# particular the nested "previous" field) is dropped at write time so the
# state file cannot grow without bound.
_PREVIOUS_SUMMARY_KEYS = (
    "ts", "status",
    "identity_hash", "constitution_hash", "symbolic_hash", "penthouse_hash",
    "memory_db_exists", "knowledge_db_exists",
    "mission_db_exists", "lift_db_exists",
    "drift",
)


def _summarize_previous(record):
    """Return a flat snapshot of the prior boot — never includes its own
    "previous" field. Bounded by `_PREVIOUS_SUMMARY_KEYS` so the size and
    nesting depth are constant per boot."""
    if not isinstance(record, dict):
        return None
    out = {k: record.get(k) for k in _PREVIOUS_SUMMARY_KEYS if k in record}
    # Preserve the count of historical boots so operators can still see
    # how many ticks have happened, without keeping the full chain.
    prior_count = record.get("history_count")
    if isinstance(prior_count, int):
        out["history_count"] = prior_count
    return out


class ContinuityCore:
    def __init__(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, rel_path):
        p = KERNEL_PACKAGE_DIR / rel_path
        if not p.exists():
            return "missing"
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def boot_check(self):
        current = {
            "ts": datetime.now(UTC).isoformat(),
            # Hash rebased kernel files by their new names within this package
            "identity_hash":      self._hash_file("identity.json"),
            "constitution_hash":  self._hash_file("constitution.md"),   # absent → "missing"
            "symbolic_hash":      self._hash_file("symbolic_core.py"),
            "penthouse_hash":     self._hash_file("kernel_core.py"),
            # DB checks remapped to tower equivalents
            "memory_db_exists":   (TOWER_DB_ROOT / "tower.sqlite").exists(),
            "knowledge_db_exists": False,   # no tower equivalent yet
            "mission_db_exists":  False,    # no tower equivalent yet
            "lift_db_exists":     (TOWER_DB_ROOT / "tower.sqlite").exists(),
        }

        previous_summary = None
        history_count = 1
        status = "FIRST_KERNEL_BOOT"

        if STATE_FILE.exists():
            try:
                prior_raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                prior_raw = None
            previous_summary = _summarize_previous(prior_raw)

            if previous_summary is not None:
                drift = []
                for key in ("identity_hash", "constitution_hash", "symbolic_hash"):
                    if previous_summary.get(key) != current.get(key):
                        drift.append(key)
                status = "CONTINUITY_CONFIRMED" if not drift else "CONTROLLED_KERNEL_DRIFT"
                current["drift"] = drift
                history_count = int(previous_summary.get("history_count") or 1) + 1

        current["status"] = status
        current["history_count"] = history_count
        # Capped to a single flat summary — never a full nested record.
        current["previous"] = previous_summary
        STATE_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current
