"""
QSB Tower V1.3 — Kernel Activation Gate

Read-only gate that evaluates all preconditions before QSBKernelCore may be
instantiated.  This module MUST NOT:
  - import QSBKernelCore
  - import the rebased kernel package
  - instantiate any kernel class
  - execute any kernel logic
  - write to rebased kernel state files
  - enable any execution flags

It reads JSON registry files and reports whether every gate condition is met.
All gate conditions must pass before activation is allowed.  Activation is
NOT allowed by this module — it only reports readiness.
"""

import json
from pathlib import Path
from datetime import datetime, UTC

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"

REBASED_K = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel"
DORMANT_K = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel"

FORBIDDEN_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]

OLD_VAULT = "/vaults/nvme0/qsb_skyscraper"


def _now():
    return datetime.now(UTC).isoformat()


def _load(path, fallback=None):
    p = Path(path)
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


class KernelActivationGate:
    """
    Evaluates all preconditions for kernel activation.

    Call evaluate() to get a full gate report.
    Call dashboard() for a concise summary.

    Neither method imports or instantiates any kernel class.
    """

    # ── Condition checks ───────────────────────────────────────────────

    def check_forbidden_paths(self):
        found = [str(p) for p in FORBIDDEN_PATHS if p.exists()]
        return {
            "gate": "forbidden_paths_absent",
            "passed": len(found) == 0,
            "detail": "All forbidden direct kernel paths absent." if not found
                      else "FORBIDDEN paths present: " + str(found),
            "found": found,
        }

    def check_kernel_not_installed(self):
        sock = _load(REG / "kernel_installation_socket.json", {})
        installed = sock.get("kernel_installed", True)
        return {
            "gate": "kernel_not_installed",
            "passed": installed is False,
            "detail": f"kernel_installed = {installed}",
            "kernel_installed": installed,
        }

    def check_operator_approval(self):
        approval = _load(REG / "operator_kernel_approval.json", {})
        recorded = approval.get("operator_approval_recorded", False)
        return {
            "gate": "operator_approval_recorded",
            "passed": recorded is True,
            "detail": "Operator approval recorded." if recorded
                      else "Operator approval NOT recorded — human must explicitly approve.",
            "operator_approval_recorded": recorded,
            "approved_by": approval.get("approved_by"),
            "approval_ts": approval.get("approval_ts"),
        }

    def check_path_rebase_complete(self):
        manifest = _load(REBASED_K / "rebase_manifest.json", {})
        if not manifest:
            return {
                "gate": "path_rebase_complete",
                "passed": False,
                "detail": "Rebase manifest not found.",
            }
        old_refs = manifest.get("old_path_references_remaining", 1)
        compile_ok = manifest.get("compile_results", {}).get("all_pass", False)
        passed = (old_refs == 0 and compile_ok)
        return {
            "gate": "path_rebase_complete",
            "passed": passed,
            "detail": f"old_path_refs={old_refs}  compile_all_pass={compile_ok}",
            "old_path_references_remaining": old_refs,
            "compile_all_pass": compile_ok,
        }

    def check_rebased_kernel_present(self):
        k_dir = REBASED_K / "kernel"
        expected = [
            "kernel_core.py", "axiom_core.py", "continuity_core.py",
            "belief_core.py", "symbolic_core.py", "identity_core.py",
            "reflection_core.py", "__init__.py",
        ]
        missing = [f for f in expected if not (k_dir / f).exists()]
        return {
            "gate": "rebased_kernel_present",
            "passed": len(missing) == 0,
            "detail": "All rebased kernel files present." if not missing
                      else "Missing: " + str(missing),
            "missing_files": missing,
        }

    def check_no_old_vault_in_rebased(self):
        k_dir = REBASED_K / "kernel"
        if not k_dir.exists():
            return {"gate": "no_old_vault_in_rebased", "passed": False,
                    "detail": "Rebased kernel directory not found."}
        remaining = []
        for py in k_dir.glob("*.py"):
            src = py.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(src.splitlines(), 1):
                if OLD_VAULT in line:
                    remaining.append(f"{py.name}:L{i}")
        passed = len(remaining) == 0
        return {
            "gate": "no_old_vault_in_rebased",
            "passed": passed,
            "detail": "Zero old vault references in rebased files." if passed
                      else "Old vault refs found: " + str(remaining),
            "old_vault_refs": remaining,
        }

    def check_state_dir_clean(self):
        state = REBASED_K / "state"
        if not state.exists():
            return {"gate": "state_dir_clean", "passed": True,
                    "detail": "State directory does not exist (kernel not run)."}
        sqlite_files = list(state.glob("*.sqlite"))
        continuity_written = (state / "continuity_state.json").exists()
        clean = len(sqlite_files) == 0 and not continuity_written
        return {
            "gate": "state_dir_clean",
            "passed": clean,
            "detail": "State dir clean — QSBKernelCore not instantiated." if clean
                      else "State files found — kernel may have been run.",
            "sqlite_files_found": [f.name for f in sqlite_files],
            "continuity_state_written": continuity_written,
            "qsb_kernel_core_instantiated": not clean,
        }

    def check_safety_flags(self):
        ac_pol = _load(REG / "agent_coordination_policy.json", {})
        ep_pol = _load(REG / "external_provider_policy.json", {})
        me_pol = _load(REG / "model_evaluation_policy.json", {})
        flags = {
            "worker_execution_enabled":   ac_pol.get("worker_execution_enabled", False),
            "live_dispatch_enabled":      ac_pol.get("live_dispatch_enabled", False),
            "provider_execution_enabled": ep_pol.get("execution_enabled", False),
            "model_inference_enabled":    me_pol.get("model_inference_enabled", False),
        }
        all_false = all(not v for v in flags.values())
        return {
            "gate": "safety_flags_all_false",
            "passed": all_false,
            "detail": "All safety flags are False." if all_false
                      else "Some safety flags are True — must be False before activation.",
            "flags": flags,
        }

    def check_security_clearance(self):
        # Read the human-recorded clearance decision from the clearance status file.
        # Clearance is never auto-granted; it must be explicitly written by a human.
        clearance = _load(REG / "security_spine_kernel_clearance_status.json", {})
        granted = clearance.get("security_clearance_granted", False) is True
        scope   = clearance.get("clearance_scope", "")
        by      = clearance.get("clearance_granted_by", "")
        spine   = clearance.get("security_spine_status", "unknown")
        if granted:
            detail = (f"Security clearance granted by {by} "
                      f"(scope: {scope}, spine: {spine}).")
        else:
            detail = ("Security clearance NOT granted. "
                      "Human must set security_clearance_granted=true in "
                      "security_spine_kernel_clearance_status.json.")
        return {
            "gate": "security_spine_clearance",
            "passed": granted,
            "detail": detail,
            "security_clearance_granted": granted,
            "clearance_scope": scope,
            "cleared_by": by,
            "security_spine_status": spine,
        }

    def check_rebased_unit_tests(self):
        # Read the unit test report generated by rebased_kernel_unit_tests.sh
        report_path = REG / "rebased_kernel_unit_test_report.json"
        if not report_path.exists():
            return {
                "gate": "rebased_kernel_unit_tests_required",
                "passed": False,
                "detail": "Rebased kernel unit test report not found. "
                          "Run scripts/rebased_kernel_unit_tests.sh first.",
                "report_exists": False,
            }
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {
                "gate": "rebased_kernel_unit_tests_required",
                "passed": False,
                "detail": f"Could not read unit test report: {e}",
            }
        all_passed = report.get("all_tests_passed", False)
        return {
            "gate": "rebased_kernel_unit_tests_required",
            "passed": all_passed,
            "detail": (f"All {report.get('tests_passed')}/{report.get('tests_run')} "
                       "rebased kernel unit tests passed." if all_passed
                       else f"Unit tests: {report.get('tests_passed')}/{report.get('tests_run')} "
                            "passed. Fix failures before activation."),
            "tests_run": report.get("tests_run"),
            "tests_passed": report.get("tests_passed"),
            "tests_failed": report.get("tests_failed"),
            "report_exists": True,
        }

    # ── Full evaluation ────────────────────────────────────────────────

    def evaluate(self):
        checks = [
            self.check_forbidden_paths(),
            self.check_kernel_not_installed(),
            self.check_operator_approval(),
            self.check_path_rebase_complete(),
            self.check_rebased_kernel_present(),
            self.check_no_old_vault_in_rebased(),
            self.check_state_dir_clean(),
            self.check_safety_flags(),
            self.check_security_clearance(),
            self.check_rebased_unit_tests(),
        ]

        passed  = [c for c in checks if c["passed"]]
        blocked = [c for c in checks if not c["passed"]]

        # activation_allowed becomes True only when ALL 10 gates pass.
        # Even then, this flag means "preconditions met, activation is permitted".
        # It does NOT install the kernel or instantiate QSBKernelCore.
        # Actual kernel instantiation is a separate explicit operator step.
        activation_allowed = len(blocked) == 0

        blocked_reasons = [
            f"[{c['gate']}] {c['detail']}" for c in blocked
        ]

        result = {
            "ts": _now(),
            "gate_status": "ALL_GATES_PASSED" if not blocked else "BLOCKED",
            "activation_allowed": activation_allowed,
            "gates_passed": len(passed),
            "gates_blocked": len(blocked),
            "blocked_reasons": blocked_reasons,
            "checks": checks,
            "forbidden_paths_absent": not any(
                Path(p).exists() for p in [
                    str(ROOT / "penthouse" / "kernel.py"),
                    str(ROOT / "penthouse" / "qsb_kernel_4_5.py"),
                    str(ROOT / "src" / "tower" / "kernel.py"),
                    str(ROOT / "src" / "tower" / "qsb_kernel_4_5.py"),
                ]
            ),
            "rebased_kernel_present": (REBASED_K / "kernel" / "kernel_core.py").exists(),
            "path_rebase_complete": self.check_path_rebase_complete()["passed"],
            "operator_approval_recorded": self.check_operator_approval()["operator_approval_recorded"],
            "security_spine_clearance": self.check_security_clearance()["security_clearance_granted"],
            "kernel_installed": self.check_kernel_not_installed()["kernel_installed"],
            "QSBKernelCore_instantiated": not self.check_state_dir_clean()["passed"],
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "next_recommended_phase": (
                "KERNEL_ACTIVATION_READY — all gates passed; operator may now call QSBKernelCore()"
                if len(blocked) == 0
                else "OPERATOR_APPROVAL_AND_FINAL_ACTIVATION"
                if len(blocked) <= 2 and all(
                    b["gate"] in ("security_spine_clearance",
                                  "operator_approval_recorded",
                                  "rebased_kernel_unit_tests_required")
                    for b in blocked
                )
                else "COMPLETE_REMAINING_GATE_CONDITIONS"
            ),
        }

        return result

    # ── Dashboard ──────────────────────────────────────────────────────

    def dashboard(self):
        r = self.evaluate()
        return {
            "module":               "kernel_activation_gate",
            "gate_status":          r["gate_status"],
            "activation_allowed":   r["activation_allowed"],
            "gates_passed":         r["gates_passed"],
            "gates_blocked":        r["gates_blocked"],
            "blocked_reasons":      r["blocked_reasons"],
            "forbidden_paths_absent": r["forbidden_paths_absent"],
            "rebased_kernel_present": r["rebased_kernel_present"],
            "path_rebase_complete": r["path_rebase_complete"],
            "operator_approval_recorded": r["operator_approval_recorded"],
            "security_spine_clearance": r["security_spine_clearance"],
            "kernel_installed":     r["kernel_installed"],
            "QSBKernelCore_instantiated": r["QSBKernelCore_instantiated"],
            "worker_execution_enabled":   False,
            "provider_execution_enabled": False,
            "model_inference_enabled":    False,
            "next_recommended_phase":     r["next_recommended_phase"],
        }
