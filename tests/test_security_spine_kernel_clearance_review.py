"""
Test the security spine kernel activation clearance review:
- clearance review report exists and is valid JSON
- security_clearance_review_complete is True
- security_clearance_recommended is True (review recommends, does not grant)
- security_clearance_granted is False (human decision required)
- activation_allowed is False
- operator_approval_recorded is False
- kernel_installed is False
- QSBKernelCore_instantiated is False
- all execution flags are False
- no blocking security findings
- forbidden active kernel paths remain absent
- state directory remains empty (kernel not instantiated)
"""
import json
import sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]

# ── Report files exist ────────────────────────────────────────────────────────
review_path  = REG / "security_spine_kernel_clearance_review.json"
status_path  = REG / "security_spine_kernel_clearance_status.json"
reports_copy = (ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel" /
                "reports" / "security_spine_clearance_review.json")

assert review_path.exists(),  "security_spine_kernel_clearance_review.json missing from registries"
assert status_path.exists(),  "security_spine_kernel_clearance_status.json missing from registries"
assert reports_copy.exists(), "security_spine_clearance_review.json missing from rebased kernel reports/"

review = json.loads(review_path.read_text())
status = json.loads(status_path.read_text())

# ── Core clearance flags ──────────────────────────────────────────────────────
cs = review["security_clearance_summary"]

assert cs["security_clearance_review_complete"] is True, \
    "security_clearance_review_complete must be True"
assert cs["security_clearance_recommended"] is True, \
    "security_clearance_recommended must be True (review passes with no blocking findings)"
assert cs["security_clearance_granted"] is False, \
    "security_clearance_granted must be False — human decision required"
assert cs["activation_allowed"] is False,           "activation_allowed must be False"
assert cs["operator_approval_recorded"] is False,   "operator_approval_recorded must be False"
assert cs["kernel_installed"] is False,             "kernel_installed must be False"
assert cs["QSBKernelCore_instantiated"] is False,   "QSBKernelCore_instantiated must be False"
assert cs["worker_execution_enabled"] is False,     "worker_execution_enabled must be False"
assert cs["provider_execution_enabled"] is False,   "provider_execution_enabled must be False"
assert cs["model_inference_enabled"] is False,      "model_inference_enabled must be False"

# ── Status file mirrors the same flags ───────────────────────────────────────
assert status["security_clearance_review_complete"] is True
assert status["security_clearance_recommended"] is True
assert status["security_clearance_granted"] is False
assert status["activation_allowed"] is False
assert status["operator_approval_recorded"] is False
assert status["kernel_installed"] is False
assert status["QSBKernelCore_instantiated"] is False

# ── No blocking findings ──────────────────────────────────────────────────────
blocking = review.get("blocking_findings", [])
assert len(blocking) == 0, \
    f"Expected 0 blocking findings, got {len(blocking)}: {blocking}"

# ── Security spine healthy ────────────────────────────────────────────────────
spine = review["security_spine_status"]
assert spine["status"] == "healthy",         f"Security spine status: {spine['status']}"
assert spine["critical_failures"] == 0,      "Security spine must have 0 critical failures"
assert spine["passed"] == spine["checks_run"], "All security spine checks must pass"

# ── All 5 floor assessments clean ────────────────────────────────────────────
for floor_key, floor_name in [
    ("floor_28_security_department",  "Security Department"),
    ("floor_29_guardian_department",  "Guardian Department"),
    ("floor_30_permissions_department","Permissions Department"),
    ("floor_31_audit_department",     "Audit Department"),
    ("floor_32_compliance_department","Compliance Department"),
]:
    floor = review.get(floor_key, {})
    assert floor.get("finding") == "NO_ISSUES", \
        f"{floor_name} ({floor_key}) finding must be NO_ISSUES, got {floor.get('finding')}"

# ── All guardian rules compliant ─────────────────────────────────────────────
guardian = review["floor_29_guardian_department"]
for rule in guardian.get("rules_detail", []):
    assert rule["status"] == "COMPLIANT", \
        f"Guardian rule {rule['id']} status: {rule['status']}"

# ── All compliance rules satisfied ───────────────────────────────────────────
compliance = review["floor_32_compliance_department"]
for rule in compliance.get("rules_compliance", []):
    assert rule["compliant"] is True, \
        f"Compliance rule {rule['rule']} is not compliant"

# ── Rebased unit tests and path rebase passed ─────────────────────────────────
assert review["rebased_kernel_unit_tests"]["all_pass"] is True
assert review["path_rebase_review"]["old_path_references_remaining"] == 0

# ── Forbidden active kernel paths absent ─────────────────────────────────────
for fp in FORBIDDEN_ACTIVE_PATHS:
    assert not fp.exists(), f"FORBIDDEN path found: {fp}"

# ── State directory empty (kernel not instantiated) ───────────────────────────
state = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel" / "state"
if state.exists():
    sqlite_files = list(state.glob("*.sqlite"))
    assert len(sqlite_files) == 0, \
        f"State SQLite files present — kernel was instantiated: {[f.name for f in sqlite_files]}"
    assert not (state / "continuity_state.json").exists(), \
        "continuity_state.json in state/ — ContinuityCore was called"

# ── Review report and status are consistent ──────────────────────────────────
assert status.get("security_clearance_granted") == cs["security_clearance_granted"]
assert status.get("activation_allowed") == cs["activation_allowed"]

# ── Next phase is set ─────────────────────────────────────────────────────────
assert review.get("next_recommended_phase") == "OPERATOR_APPROVAL_AND_FINAL_ACTIVATION", \
    f"Unexpected next phase: {review.get('next_recommended_phase')}"

print("SECURITY SPINE KERNEL CLEARANCE REVIEW TEST PASSED")
print(f"  review_complete             : {cs['security_clearance_review_complete']}")
print(f"  clearance_recommended       : {cs['security_clearance_recommended']}")
print(f"  clearance_GRANTED           : {cs['security_clearance_granted']}  (human decision required)")
print(f"  activation_allowed          : {cs['activation_allowed']}")
print(f"  operator_approval_recorded  : {cs['operator_approval_recorded']}")
print(f"  kernel_installed            : {cs['kernel_installed']}")
print(f"  QSBKernelCore_instantiated  : {cs['QSBKernelCore_instantiated']}")
print(f"  blocking_findings           : {len(blocking)}")
print(f"  security_spine              : {spine['status']}  ({spine['passed']}/{spine['checks_run']})")
print(f"  all_guardian_rules          : COMPLIANT")
print(f"  all_compliance_rules        : COMPLIANT")
print(f"  forbidden_paths             : all absent")
print(f"  state_dir_sqlite_files      : 0")
print(f"  next_phase                  : {review['next_recommended_phase']}")
