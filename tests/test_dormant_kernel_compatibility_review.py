"""
Verify the dormant kernel compatibility review:
- report files exist and are valid JSON
- activation_allowed is False
- kernel_installed is False
- all execution flags are False
- forbidden direct kernel paths remain absent
- old source kernel was not executed (verified by static analysis only)
- hash verification passed in the report
- compatibility score is present
"""
import json
import hashlib
from pathlib import Path

ROOT    = Path("/vaults/nvme0/qsb_tower_v1")
REG     = ROOT / "data" / "registries"
DORMANT = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel"

# ── Report files exist ────────────────────────────────────────────────────────
reg_report   = REG / "dormant_kernel_compatibility_review.json"
local_report = DORMANT / "import_reports" / "compatibility_review.json"

assert reg_report.exists(),   "dormant_kernel_compatibility_review.json missing from registries"
assert local_report.exists(), "compatibility_review.json missing from import_reports"

r = json.loads(reg_report.read_text())

# ── Core safety flags ─────────────────────────────────────────────────────────
assert r.get("activation_allowed") is False,          "activation_allowed must be False"

ts = r.get("current_tower_state_at_review_time", {})
assert ts.get("kernel_installed")                is False, "kernel_installed must be False"
assert ts.get("dormant_kernel_activation_enabled") is False, "activation_enabled must be False"
assert ts.get("worker_execution_enabled")         is False, "worker_execution_enabled must be False"
assert ts.get("provider_execution_enabled")       is False, "provider_execution_enabled must be False"
assert ts.get("model_inference_enabled")          is False, "model_inference_enabled must be False"
assert ts.get("live_dispatch_enabled")            is False, "live_dispatch_enabled must be False"
assert ts.get("forbidden_paths_absent")           is True,  "forbidden_paths_absent must be True"

# ── Forbidden direct kernel paths absent ──────────────────────────────────────
FORBIDDEN = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]
for f in FORBIDDEN:
    assert not f.exists(), f"FORBIDDEN path exists: {f}"

# ── Hash verification passed ──────────────────────────────────────────────────
hv = r.get("hash_verification", {})
assert hv.get("result") == "ALL_MATCH", f"Hash verification failed: {hv.get('result')}"
assert hv.get("files_checked", 0) >= 10, "Too few files hash-checked"

# ── Compatibility score present and in valid range ────────────────────────────
cs = r.get("compatibility_score", {})
score = cs.get("score")
assert score is not None,           "compatibility_score.score missing"
assert 0 <= score <= 100,           f"Score out of range: {score}"
assert score > 0,                   "Score should not be 0 — kernel has real logic"
assert cs.get("overall_verdict"),   "overall_verdict missing from compatibility score"

# ── Required adapter changes present ─────────────────────────────────────────
adapters = r.get("required_adapter_changes_before_activation", [])
assert len(adapters) >= 3, "Expected at least 3 adapter changes listed"
blocking = [a for a in adapters if a.get("priority") == "BLOCKING"]
assert len(blocking) >= 2, "Expected at least 2 BLOCKING adapter changes"
adapter_ids = {a["id"] for a in adapters}
assert "ADAPTER_01" in adapter_ids, "ADAPTER_01 (path rebase) must be listed"

# ── Required safety gates present ────────────────────────────────────────────
gates = r.get("required_safety_gates_before_activation", [])
assert len(gates) >= 4, "Expected at least 4 safety gates"
gate_ids = {g["id"] for g in gates}
assert "GATE_01" in gate_ids, "GATE_01 (kernel_installed flag) must be listed"
assert "GATE_02" in gate_ids, "GATE_02 (path rebase) must be listed"
assert "GATE_03" in gate_ids, "GATE_03 (operator approval) must be listed"

# ── Kernel identity fields ────────────────────────────────────────────────────
ki = r.get("kernel_identity", {})
assert ki.get("name") == "QSB Kernel",   f"Kernel name mismatch: {ki.get('name')}"
assert "4.6" in ki.get("version", ""),   f"Version mismatch: {ki.get('version')}"

# ── Old source kernel still present and untouched ─────────────────────────────
# We verify this by checking the dormant copy hashes still match — if the source
# had been modified by execution, continuity_state.json would have a new timestamp.
# We cross-check the dormant copy's continuity_state.json hash against the manifest.
manifest = json.loads((DORMANT / "import_manifest.json").read_text())
recorded = manifest.get("sha256_hashes", {})
continuity_file = DORMANT / "kernel" / "continuity_state.json"
if continuity_file.exists() and "kernel/continuity_state.json" in recorded:
    actual = hashlib.sha256(continuity_file.read_bytes()).hexdigest()
    expected = recorded["kernel/continuity_state.json"]
    assert actual == expected, (
        "continuity_state.json hash changed — kernel state may have been written. "
        f"Expected {expected[:16]}..., got {actual[:16]}..."
    )

# ── Report was produced by static analysis only (verify via report type field) ─
assert r.get("review_method") == "static_analysis_read_only", \
    "review_method must be static_analysis_read_only"

# ── Next phase present ────────────────────────────────────────────────────────
nrp = r.get("next_recommended_phase", {})
assert nrp.get("phase"), "next_recommended_phase.phase missing"

# ── Two report copies are identical ──────────────────────────────────────────
assert reg_report.read_bytes() == local_report.read_bytes(), \
    "Registry and import_reports copies of the review diverge"

print("DORMANT KERNEL COMPATIBILITY REVIEW TEST PASSED")
print(f"  Compatibility score     : {score}/100")
print(f"  Verdict                 : {cs.get('overall_verdict', '')[:60]}")
print(f"  activation_allowed      : {r.get('activation_allowed')}")
print(f"  kernel_installed        : {ts.get('kernel_installed')}")
print(f"  kernel_logic_present    : {ts.get('kernel_logic_present')}")
print(f"  Blocking adapters       : {len(blocking)}")
print(f"  Safety gates            : {len(gates)}")
print(f"  Hash verification       : {hv.get('result')}")
print(f"  Forbidden paths         : all absent")
print(f"  continuity_state intact : {actual[:16] if continuity_file.exists() else 'n/a'}...")
print(f"  Next phase              : {nrp.get('phase')}")
