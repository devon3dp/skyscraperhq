"""
QSB Tower V1.3 — Dormant Kernel Adapter

READ-ONLY adapter for inspecting the dormant imported kernel package.
This module MUST NOT:
  - instantiate QSBKernelCore or any kernel sub-core class
  - run executive/penthouse.py
  - call any model, Ollama, or external provider
  - write to old skyscraper memory or state paths
  - enable workers, provider execution, or model inference

It MAY:
  - read identity.json as static JSON
  - read continuity_state.json as static JSON
  - list imported files
  - verify SHA-256 hashes against the manifest
  - report compatibility status
  - expose a dashboard() summary
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, UTC

ROOT   = Path("/vaults/nvme0/qsb_tower_v1")
DORMANT_DIR = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel"
KERNEL_DIR  = DORMANT_DIR / "kernel"
SUPPORT_DIR = DORMANT_DIR / "source_support"
MANIFEST    = DORMANT_DIR / "import_manifest.json"
IDENTITY    = KERNEL_DIR / "identity.json"
CONTINUITY  = KERNEL_DIR / "continuity_state.json"

# Forbidden paths — verified absent on every adapter call
FORBIDDEN_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]


def _now():
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return "unreadable"


class DormantKernelAdapter:
    """
    Provides read-only inspection of the dormant imported kernel.
    Never instantiates any kernel class or runs kernel logic.
    """

    # ── Internal helpers ───────────────────────────────────────────────

    def _load_manifest(self) -> dict:
        if MANIFEST.exists():
            try:
                return json.loads(MANIFEST.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _read_identity(self) -> dict:
        """Read identity.json as static data — no class instantiation."""
        if IDENTITY.exists():
            try:
                return json.loads(IDENTITY.read_text(encoding="utf-8"))
            except Exception:
                return {"error": "unreadable"}
        return {"error": "identity.json not found in dormant import"}

    def _read_continuity_state(self) -> dict:
        """Read continuity_state.json as static data — no class instantiation."""
        if CONTINUITY.exists():
            try:
                return json.loads(CONTINUITY.read_text(encoding="utf-8"))
            except Exception:
                return {"error": "unreadable"}
        return {"error": "continuity_state.json not found in dormant import"}

    # ── Public inspection methods ──────────────────────────────────────

    def list_imported_files(self) -> dict:
        """Return lists of all files in the dormant import directories."""
        kernel_files  = sorted(p.name for p in KERNEL_DIR.iterdir()
                               if p.is_file() and not p.name.startswith("__pycache__")) \
                        if KERNEL_DIR.exists() else []
        support_files = sorted(p.name for p in SUPPORT_DIR.iterdir()
                               if p.is_file()) \
                        if SUPPORT_DIR.exists() else []
        return {
            "kernel_dir":  str(KERNEL_DIR),
            "kernel_files": kernel_files,
            "support_dir":  str(SUPPORT_DIR),
            "support_files": support_files,
            "total": len(kernel_files) + len(support_files),
        }

    def verify_hashes(self) -> dict:
        """
        Compare actual SHA-256 hashes of dormant files against manifest.
        Returns per-file pass/fail and an overall result.
        """
        manifest = self._load_manifest()
        recorded = manifest.get("sha256_hashes", {})
        if not recorded:
            return {"status": "no_manifest_hashes", "results": {}}

        results = {}
        all_match = True
        for rel_path, expected_hash in recorded.items():
            full = DORMANT_DIR / rel_path
            actual = _sha256(full)
            match = (actual == expected_hash)
            if not match:
                all_match = False
            results[rel_path] = {
                "expected": expected_hash,
                "actual":   actual,
                "match":    match,
            }

        return {
            "status": "all_match" if all_match else "hash_drift_detected",
            "files_checked": len(results),
            "results": results,
        }

    def check_forbidden_paths(self) -> dict:
        """Verify that all four forbidden kernel paths remain absent."""
        found = []
        for p in FORBIDDEN_PATHS:
            if p.exists():
                found.append(str(p))
        return {
            "all_absent": len(found) == 0,
            "found": found,
            "checked": [str(p) for p in FORBIDDEN_PATHS],
        }

    def compatibility_summary(self) -> dict:
        """
        Static analysis summary from the manifest — no code execution.
        """
        manifest = self._load_manifest()
        compat = manifest.get("compatibility_summary", {})
        risks = []
        if compat.get("hardcoded_old_root"):
            risks.append("All kernel modules hardcode /vaults/nvme0/qsb_skyscraper ROOT path")
        if compat.get("requires_path_rebase_before_activation"):
            risks.append("Path rebase required before activation")
        if compat.get("requires_old_skyscraper_module_replacement"):
            risks.append("Old skyscraper module references must be replaced with tower equivalents")
        if compat.get("penthouse_py_must_not_be_run"):
            risks.append("executive/penthouse.py must not be run (interactive loop + Ollama dependency)")
        return {
            "risks_count": len(risks),
            "risks": risks,
            "safe_for_dormant_import": True,
            "safe_to_instantiate_kernel_classes": False,
            "required_before_activation": [
                "path_rebase_layer",
                "old_module_replacement",
                "operator_approval",
            ],
        }

    # ── Dashboard ──────────────────────────────────────────────────────

    def dashboard(self) -> dict:
        """
        Read-only status summary. Safe to call repeatedly.
        Never instantiates kernel classes.
        """
        manifest   = self._load_manifest()
        identity   = self._read_identity()
        continuity = self._read_continuity_state()
        files      = self.list_imported_files()
        forbidden  = self.check_forbidden_paths()
        hashes     = self.verify_hashes()
        compat     = self.compatibility_summary()

        safety = manifest.get("safety_flags", {})

        return {
            "adapter":                  "dormant_kernel_adapter",
            "ts":                       _now(),
            "dormant_import_dir":       str(DORMANT_DIR),
            "dormant_kernel_imported":  DORMANT_DIR.exists(),

            "kernel_name":    identity.get("name",    "unknown"),
            "kernel_version": identity.get("version", "unknown"),
            "kernel_role":    identity.get("role",    "unknown"),
            "kernel_principle": identity.get("principle", "unknown"),

            "continuity_status": continuity.get("status", "unknown"),
            "continuity_ts":     continuity.get("ts",     "unknown"),

            "imported_files_total": files["total"],
            "kernel_files":         files["kernel_files"],
            "support_files":        files["support_files"],

            "hash_verification":    hashes["status"],
            "hashes_checked":       hashes.get("files_checked", 0),

            "forbidden_paths_absent": forbidden["all_absent"],
            "forbidden_paths_found":  forbidden["found"],

            "compatibility_risks":  compat["risks_count"],

            "kernel_installed":             False,
            "kernel_logic_present":         True,
            "execution_enabled":            safety.get("execution_enabled",            False),
            "worker_execution_enabled":     safety.get("worker_execution_enabled",     False),
            "provider_execution_enabled":   safety.get("provider_execution_enabled",   False),
            "model_inference_enabled":      safety.get("model_inference_enabled",      False),
            "live_dispatch_enabled":        safety.get("live_dispatch_enabled",        False),
            "activation_enabled":           safety.get("activation_enabled",           False),
            "direct_execution_allowed":     safety.get("direct_execution_allowed",     False),
            "requires_adapter":             safety.get("requires_adapter",             True),
            "requires_operator_approval":   safety.get("requires_operator_approval_before_activation", True),

            "next_step": "compatibility_review_before_activation",
        }


if __name__ == "__main__":
    print(json.dumps(DormantKernelAdapter().dashboard(), indent=2))
