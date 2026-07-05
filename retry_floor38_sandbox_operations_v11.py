from pathlib import Path
from datetime import datetime, UTC
import json, os, textwrap

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def now():
    return datetime.now(UTC).isoformat()

def write(rel, text, mode=None):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    if mode is not None:
        os.chmod(p, mode)
    return p

def write_json(rel, obj):
    return write(rel, json.dumps(obj, indent=2))

print("============================================================")
print(" QSB TOWER — FLOOR 38 SANDBOX OPERATIONS V1.1 RETRY")
print(" Sealed metadata envelopes only. No execution.")
print("============================================================")

# ------------------------------------------------------------
# Directories
# ------------------------------------------------------------
for rel in [
    "floors/floor_38_sandbox_operations",
    "floors/floor_38_sandbox_operations/sandbox_reports",
    "floors/floor_38_sandbox_operations/task_envelopes",
    "floors/floor_38_sandbox_operations/containment_rules",
    "data/registries",
    "data/db",
    "config",
    "scripts",
    "tests",
    "src/tower",
]:
    (ROOT / rel).mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# Registries
# ------------------------------------------------------------
policy = {
    "version": "1.1",
    "floor": "floor_38",
    "department": "Sandbox Operations",
    "sandbox_only": True,
    "dry_run_only": True,
    "containment_mode": "sealed_metadata_envelopes_only",
    "kernel_installed": False,
    "kernel_logic_present": False,
    "execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
    "autonomous_workers_enabled": False,
    "live_dispatch_enabled": False,
    "shell_execution_enabled": False,
    "filesystem_write_enabled": False,
    "network_enabled": False,
    "real_process_spawn_enabled": False,
    "notice": "Floor 38 contains simulated task envelopes only. It does not execute workers, providers, models, shell commands, or kernel logic."
}

rules = [
    ["no_shell_execution", "shell_execution_enabled", False],
    ["no_filesystem_writes", "filesystem_write_enabled", False],
    ["no_network", "network_enabled", False],
    ["no_model_inference", "model_inference_enabled", False],
    ["no_worker_execution", "worker_execution_enabled", False],
    ["no_provider_execution", "provider_execution_enabled", False],
    ["no_kernel_installation", "kernel_installed", False],
    ["dry_run_only", "dry_run_only", True],
    ["sealed_required", "sealed", True],
]

rules = [
    {
        "rule_id": rid,
        "field": field,
        "required_value": value,
        "description": f"{field} must equal {value}"
    }
    for rid, field, value in rules
]

base_envelope = {
    "dry_run_only": True,
    "sealed": True,
    "shell_execution_enabled": False,
    "filesystem_write_enabled": False,
    "network_enabled": False,
    "model_inference_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "kernel_installed": False,
}

envelopes = []
for envelope_id, name, candidate_id, task_type, expected in [
    ("sandbox_claude_code_audit_envelope", "Claude Code read-only audit sandbox", "claude_code", "read_only_audit_simulation", "contained_readonly_audit_envelope"),
    ("sandbox_openclaw_source_audit_envelope", "OpenClaw source-audit placeholder sandbox", "openclaw", "source_audit_placeholder", "blocked_until_source_audit"),
    ("sandbox_model_route_envelope", "Model request route containment sandbox", "ollama_local_models", "model_route_simulation", "route_contained_no_inference"),
    ("sandbox_security_gate_envelope", "Security gate containment sandbox", "future_llm_provider", "security_gate_simulation", "provider_blocked_until_socket_approved"),
    ("sandbox_emergency_fallback_envelope", "Emergency Stairwell fallback sandbox", "none", "emergency_fallback_simulation", "fallback_contained_no_execution"),
]:
    e = dict(base_envelope)
    e.update({
        "envelope_id": envelope_id,
        "name": name,
        "source_floor": "floor_37",
        "target_floor": "floor_38",
        "candidate_id": candidate_id,
        "task_type": task_type,
        "allowed_mode": "metadata_only",
        "expected_result": expected,
    })
    envelopes.append(e)

write_json("data/registries/sandbox_operations_policy.json", policy)
write_json("data/registries/sandbox_containment_rules.json", rules)
write_json("data/registries/sandbox_task_envelopes.json", envelopes)
write_json("floors/floor_38_sandbox_operations/containment_rules/sandbox_containment_rules.json", rules)
write_json("floors/floor_38_sandbox_operations/task_envelopes/sandbox_task_envelopes.json", envelopes)

write_json("floors/floor_38_sandbox_operations/floor_manifest.json", {
    "floor_id": "floor_38",
    "number": 38,
    "department": "Sandbox Operations",
    "version": "1.1",
    "zone": "ZONE C",
    "status": "online",
    "role": "Isolated dry-run containment for simulated tasks and candidate worker envelopes.",
    **policy,
    "hardwired_providers": False,
    "providers_are_external": True,
    "models_are_temporary_tenants": True,
    "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
    "routes_through": {
        "simulation_labs": "floor_37",
        "candidate_workers": "floor_25",
        "model_evaluation": "floor_26",
        "security": "floor_28_floor_32",
        "diagnostics": "floor_33",
        "monitoring": "floor_34"
    },
    "created_or_verified": now(),
})

write("floors/floor_38_sandbox_operations/README.md", """
# Floor 38 — Sandbox Operations

Floor 38 contains simulated tasks inside sealed metadata envelopes.

Safety:
- No shell execution
- No filesystem writes
- No network access
- No model inference
- No provider calls
- No worker activation
- No QSB Kernel installation

This is not a real execution sandbox. It is a containment registry and dry-run validation floor.
""")

write("config/sandbox_operations.yaml", """
sandbox_operations:
  version: 1.1
  floor: floor_38
  department: Sandbox Operations
  sandbox_only: true
  dry_run_only: true
  containment_mode: sealed_metadata_envelopes_only
  execution_enabled: false
  worker_execution_enabled: false
  provider_execution_enabled: false
  model_inference_enabled: false
  shell_execution_enabled: false
  filesystem_write_enabled: false
  network_enabled: false
  real_process_spawn_enabled: false
  kernel_installed: false
  kernel_logic_present: false
""")

# ------------------------------------------------------------
# Module
# ------------------------------------------------------------
write("src/tower/sandbox_operations.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json, sqlite3, hashlib

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
DB = ROOT / "data" / "db" / "sandbox_operations.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(rel, fallback):
    p = ROOT / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else fallback

SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    status TEXT,
    envelopes INTEGER,
    contained INTEGER,
    rejected INTEGER,
    critical_failures INTEGER,
    warnings INTEGER,
    details TEXT
);
"""

class SandboxOperations:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("data/registries/sandbox_operations_policy.json", {})

    def rules(self):
        return load_json("data/registries/sandbox_containment_rules.json", [])

    def envelopes(self):
        return load_json("data/registries/sandbox_task_envelopes.json", [])

    def floor_manifest(self):
        return load_json("floors/floor_38_sandbox_operations/floor_manifest.json", {})

    def inspect_envelope(self, envelope):
        failures = []
        for rule in self.rules():
            field = rule["field"]
            required = rule["required_value"]
            actual = envelope.get(field)
            if actual != required:
                failures.append({
                    "rule_id": rule["rule_id"],
                    "field": field,
                    "required": required,
                    "actual": actual
                })

        raw = json.dumps(envelope, sort_keys=True)
        envelope_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        contained = len(failures) == 0

        return {
            "ts": now(),
            "envelope_id": envelope.get("envelope_id"),
            "envelope_hash": envelope_hash,
            "name": envelope.get("name"),
            "status": "contained" if contained else "rejected",
            "containment_status": "contained_dry_run_only" if contained else "contained_rejected",
            "risk_level": "low" if contained else "high",
            "sandbox_only": True,
            "dry_run_only": True,
            "sealed": envelope.get("sealed"),
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "shell_execution_enabled": False,
            "filesystem_write_enabled": False,
            "network_enabled": False,
            "kernel_installed": False,
            "candidate_id": envelope.get("candidate_id"),
            "task_type": envelope.get("task_type"),
            "failures": failures,
            "result": envelope.get("expected_result") if contained else "envelope_rejected_by_containment_rules"
        }

    def run_all(self):
        policy = self.policy()
        manifest = self.floor_manifest()
        envelopes = self.envelopes()
        runs = [self.inspect_envelope(e) for e in envelopes]

        required_false = [
            "execution_enabled",
            "worker_execution_enabled",
            "provider_execution_enabled",
            "model_inference_enabled",
            "shell_execution_enabled",
            "filesystem_write_enabled",
            "network_enabled",
            "real_process_spawn_enabled",
            "kernel_installed",
        ]

        critical_failures = 0
        for key in required_false:
            if policy.get(key) is not False:
                critical_failures += 1
            if manifest.get(key) is not False:
                critical_failures += 1

        rejected = [r for r in runs if r["status"] != "contained"]
        critical_failures += len(rejected)

        warnings = 0
        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        report = {
            "ts": now(),
            "floor": "floor_38",
            "department": "Sandbox Operations",
            "version": "1.1",
            "status": status,
            "sandbox_only": True,
            "dry_run_only": True,
            "containment_mode": "sealed_metadata_envelopes_only",
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "autonomous_workers_enabled": False,
            "live_dispatch_enabled": False,
            "shell_execution_enabled": False,
            "filesystem_write_enabled": False,
            "network_enabled": False,
            "real_process_spawn_enabled": False,
            "envelope_count": len(envelopes),
            "contained_envelopes": len([r for r in runs if r["status"] == "contained"]),
            "rejected_envelopes": len(rejected),
            "critical_failures": critical_failures,
            "warnings": warnings,
            "runs": runs,
            "activation_recommendation": "sandbox_only_do_not_execute_workers_or_providers",
            "next_recommended_phase": "Dashboard V1.4 Polish or Floor 39 Development Labs V1.1"
        }

        out = ROOT / "floors" / "floor_38_sandbox_operations" / "sandbox_reports" / "latest_sandbox_operations_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        reg = ROOT / "data" / "registries" / "sandbox_operations_latest_runs.json"
        reg.write_text(json.dumps(runs, indent=2), encoding="utf-8")

        self.conn.execute(
            "INSERT INTO sandbox_reports(ts,status,envelopes,contained,rejected,critical_failures,warnings,details) VALUES (?,?,?,?,?,?,?,?)",
            (report["ts"], status, report["envelope_count"], report["contained_envelopes"], report["rejected_envelopes"], critical_failures, warnings, json.dumps(report))
        )
        self.conn.commit()

        return report

    def recent_reports(self, limit=6):
        rows = self.conn.execute("SELECT * FROM sandbox_reports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_all()
        return {
            "floor": "floor_38",
            "department": "Sandbox Operations",
            "status": report["status"],
            "sandbox_only": True,
            "dry_run_only": True,
            "containment_mode": report["containment_mode"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "shell_execution_enabled": False,
            "filesystem_write_enabled": False,
            "network_enabled": False,
            "real_process_spawn_enabled": False,
            "envelope_count": report["envelope_count"],
            "contained_envelopes": report["contained_envelopes"],
            "rejected_envelopes": report["rejected_envelopes"],
            "critical_failures": report["critical_failures"],
            "warnings": report["warnings"],
            "activation_recommendation": report["activation_recommendation"],
            "latest_report": "floors/floor_38_sandbox_operations/sandbox_reports/latest_sandbox_operations_report.json",
            "recent_reports": self.recent_reports(6),
            "next_recommended_phase": report["next_recommended_phase"]
        }

if __name__ == "__main__":
    print(json.dumps(SandboxOperations().dashboard(), indent=2))
''')

# ------------------------------------------------------------
# Scripts
# ------------------------------------------------------------
write("scripts/sandbox_operations_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.sandbox_operations
""", mode=0o755)

write("scripts/run_floor38_sandboxes.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.sandbox_operations import SandboxOperations
import json
r = SandboxOperations().run_all()
print(json.dumps({
    "floor": r["floor"],
    "department": r["department"],
    "status": r["status"],
    "sandbox_only": r["sandbox_only"],
    "dry_run_only": r["dry_run_only"],
    "envelope_count": r["envelope_count"],
    "contained_envelopes": r["contained_envelopes"],
    "rejected_envelopes": r["rejected_envelopes"],
    "critical_failures": r["critical_failures"],
    "warnings": r["warnings"],
    "worker_execution_enabled": r["worker_execution_enabled"],
    "provider_execution_enabled": r["provider_execution_enabled"],
    "model_inference_enabled": r["model_inference_enabled"],
    "network_enabled": r["network_enabled"],
    "activation_recommendation": r["activation_recommendation"]
}, indent=2))
PY2
""", mode=0o755)

# ------------------------------------------------------------
# Tests
# ------------------------------------------------------------
write("tests/test_sandbox_operations_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.sandbox_operations import SandboxOperations

sb = SandboxOperations()
r = sb.run_all()

assert r['floor'] == 'floor_38'
assert r['sandbox_only'] is True
assert r['dry_run_only'] is True
assert r['kernel_installed'] is False
assert r['kernel_logic_present'] is False
assert r['execution_enabled'] is False
assert r['worker_execution_enabled'] is False
assert r['provider_execution_enabled'] is False
assert r['model_inference_enabled'] is False
assert r['shell_execution_enabled'] is False
assert r['filesystem_write_enabled'] is False
assert r['network_enabled'] is False
assert r['real_process_spawn_enabled'] is False
assert r['envelope_count'] >= 5
assert r['contained_envelopes'] == r['envelope_count'], r
assert r['rejected_envelopes'] == 0, r
assert r['critical_failures'] == 0, r
assert r['warnings'] == 0, r

print('FLOOR 38 SANDBOX OPERATIONS V1.1 VALIDATION PASSED')
print('Status:', r['status'])
print('Envelopes:', r['envelope_count'])
print('Contained:', r['contained_envelopes'])
print('Rejected:', r['rejected_envelopes'])
print('Critical failures:', r['critical_failures'])
print('Warnings:', r['warnings'])
print('Recommendation:', r['activation_recommendation'])
""")

# ------------------------------------------------------------
# Dashboard patch
# ------------------------------------------------------------
server_path = ROOT / "src/dashboard/server.py"
dashboard_patched = False

if server_path.exists():
    server = server_path.read_text(encoding="utf-8")
    (ROOT / "src/dashboard/server.py.backup_before_floor38_retry").write_text(server, encoding="utf-8")

    replacements = [
        (
            '"simulation_labs": safe_dashboard("tower.simulation_labs", "SimulationLabs")',
            '"simulation_labs": safe_dashboard("tower.simulation_labs", "SimulationLabs"),\\n        "sandbox_operations": safe_dashboard("tower.sandbox_operations", "SandboxOperations")'
        ),
        (
            '"/api/simulation_labs": ("tower.simulation_labs", "SimulationLabs")',
            '"/api/simulation_labs": ("tower.simulation_labs", "SimulationLabs"),\\n            "/api/sandbox_operations": ("tower.sandbox_operations", "SandboxOperations")'
        ),
        (
            '"floor_37": "simulation_labs",',
            '"floor_37": "simulation_labs",\\n    "floor_38": "sandbox_operations",'
        ),
        (
            "const simLabs = data.simulation_labs || {};",
            "const simLabs = data.simulation_labs || {};\\n  const sandboxOps = data.sandbox_operations || {};"
        ),
    ]

    for old, new in replacements:
        if old in server and new not in server:
            server = server.replace(old, new)
            dashboard_patched = True

    panel = '''
    <div class="panel">
      <h2>Floor 38 Sandbox Operations <span class="badge good">contained</span></h2>
      <div class="panel-grid" id="sandboxGrid"></div>
    </div>
'''
    if 'id="sandboxGrid"' not in server:
        marker = '''    <div class="panel">
      <h2>Lift Network <span class="badge blue">click lift</span></h2>'''
        if marker in server:
            server = server.replace(marker, panel + "\\n" + marker)
            dashboard_patched = True

    render = '''
  renderGrid("sandboxGrid", [
    ["Status", safe(sandboxOps.status), sandboxOps.status === "healthy" ? "good" : "warn"],
    ["Envelopes", safe(sandboxOps.envelope_count), "blue"],
    ["Contained", safe(sandboxOps.contained_envelopes), "good"],
    ["Rejected", safe(sandboxOps.rejected_envelopes), sandboxOps.rejected_envelopes ? "bad" : "good"],
    ["Network", yesNo(sandboxOps.network_enabled), sandboxOps.network_enabled ? "bad" : "good"],
    ["Mode", sandboxOps.dry_run_only ? "sealed_metadata" : "unknown", "blue"]
  ]);
'''
    if 'renderGrid("sandboxGrid"' not in server:
        marker = '  renderGrid("simulationGrid", ['
        idx = server.find(marker)
        if idx >= 0:
            # insert after the simulationGrid render block by finding the next "  ]);"
            end = server.find("  ]);", idx)
            if end >= 0:
                end += len("  ]);")
                server = server[:end] + "\\n\\n" + render + server[end:]
                dashboard_patched = True

    server_path.write_text(server, encoding="utf-8")

write("tests/test_dashboard_floor38_v11.py", """
import sys, importlib.util, py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src/dashboard/server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor38', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()
assert 'sandbox_operations' in payload, 'sandbox_operations missing from live_payload'
sb = payload['sandbox_operations']

assert sb['floor'] == 'floor_38'
assert sb['sandbox_only'] is True
assert sb['dry_run_only'] is True
assert sb['worker_execution_enabled'] is False
assert sb['provider_execution_enabled'] is False
assert sb['model_inference_enabled'] is False
assert sb['network_enabled'] is False
assert sb['critical_failures'] == 0

print('DASHBOARD FLOOR 38 V1.1 VALIDATION PASSED')
print('Status:', sb['status'])
print('Envelopes:', sb['envelope_count'])
print('Contained:', sb['contained_envelopes'])
print('Rejected:', sb['rejected_envelopes'])
print('Network:', sb['network_enabled'])
print('HTML panel present:', 'id="sandboxGrid"' in mod.HTML)
""")

print()
print("Floor 38 Sandbox Operations retry installed.")
print("Dashboard patched:", dashboard_patched)
print("No worker execution. No provider execution. No model inference. No kernel.")
