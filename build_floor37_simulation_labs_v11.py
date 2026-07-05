from pathlib import Path
from datetime import datetime, UTC
import json
import os
import textwrap

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def now():
    return datetime.now(UTC).isoformat()

def write(rel, text, mode=None):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    if mode is not None:
        os.chmod(path, mode)
    return path

def write_json(rel, obj):
    return write(rel, json.dumps(obj, indent=2))

print("============================================================")
print(" QSB TOWER — FLOOR 37 SIMULATION LABS V1.1")
print(" Dry-run simulations only. No workers. No providers. No kernel.")
print("============================================================")

for rel in [
    "floors/floor_37_simulation_labs",
    "floors/floor_37_simulation_labs/simulation_registry",
    "floors/floor_37_simulation_labs/simulation_reports",
    "floors/floor_37_simulation_labs/scenario_library",
    "data/registries",
    "data/db",
    "config",
    "scripts",
    "tests",
    "src/tower",
]:
    (ROOT / rel).mkdir(parents=True, exist_ok=True)

policy = {
    "version": "1.1",
    "floor": "floor_37",
    "department": "Simulation Labs",
    "role": "Dry-run simulation of candidate workers, lift paths, sealed packets, routing decisions, and building readiness.",
    "kernel_required": False,
    "kernel_installed": False,
    "kernel_logic_present": False,
    "models_required": False,
    "execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
    "autonomous_workers_enabled": False,
    "live_dispatch_enabled": False,
    "simulation_only": True,
    "dry_run_only": True,
    "writes_real_lift_packets": False,
    "calls_external_providers": False,
    "activates_candidates": False,
    "principle": "Floor 37 simulates future movement without moving real workers or executing providers."
}

scenarios = [
    {
        "scenario_id": "candidate_worker_readonly_audit",
        "name": "Claude Code read-only audit simulation",
        "description": "Simulates Claude Code inspecting the tower as an external read-only candidate.",
        "source_floor": "floor_25",
        "route": ["floor_25", "floor_26", "floor_33", "floor_31"],
        "lifts": ["main_mid_rise", "service_lift", "security_lift"],
        "packet_type": "simulated_readonly_audit_packet",
        "candidate_id": "claude_code",
        "execution_enabled": False,
        "expected_result": "audit_allowed_readonly"
    },
    {
        "scenario_id": "candidate_model_evaluation_gate",
        "name": "Candidate model evaluation gate simulation",
        "description": "Simulates Floor 25 sending candidates to Floor 26 for static evaluation.",
        "source_floor": "floor_25",
        "route": ["floor_25", "floor_26"],
        "lifts": ["main_mid_rise", "service_lift"],
        "packet_type": "simulated_candidate_evaluation_packet",
        "candidate_id": "all_candidates",
        "execution_enabled": False,
        "expected_result": "candidate_only_do_not_activate"
    },
    {
        "scenario_id": "model_request_safe_route",
        "name": "Safe model request route simulation",
        "description": "Simulates a coding request travelling to Floor 24, then to Floor 27 inventory or Floor 23 sockets.",
        "source_floor": "floor_05",
        "route": ["floor_05", "floor_24", "floor_27"],
        "lifts": ["service_lift", "model_lift"],
        "packet_type": "simulated_model_route_packet",
        "candidate_id": "ollama_local_models",
        "execution_enabled": False,
        "expected_result": "route_valid_no_inference"
    },
    {
        "scenario_id": "security_precheck_route",
        "name": "Security precheck simulation",
        "description": "Simulates future candidate activation request being routed through the Security Spine.",
        "source_floor": "floor_25",
        "route": ["floor_25", "floor_28", "floor_29", "floor_30", "floor_31", "floor_32"],
        "lifts": ["security_lift"],
        "packet_type": "simulated_security_precheck_packet",
        "candidate_id": "openclaw",
        "execution_enabled": False,
        "expected_result": "blocked_until_source_audit"
    },
    {
        "scenario_id": "emergency_stairwell_fallback",
        "name": "Emergency Stairwell fallback simulation",
        "description": "Simulates safe fallback from Penthouse to Basement if lifts are unavailable.",
        "source_floor": "penthouse",
        "route": ["penthouse", "floor_53", "ground", "B1", "B2", "B3"],
        "lifts": ["emergency_stairwell"],
        "packet_type": "simulated_emergency_fallback_packet",
        "candidate_id": "none",
        "execution_enabled": False,
        "expected_result": "fallback_path_available"
    }
]

write_json("data/registries/simulation_labs_policy.json", policy)
write_json("data/registries/simulation_scenarios.json", scenarios)

write_json("floors/floor_37_simulation_labs/floor_manifest.json", {
    "floor_id": "floor_37",
    "number": 37,
    "department": "Simulation Labs",
    "version": "1.1",
    "zone": "ZONE C",
    "status": "online",
    "role": "Dry-run simulation of future worker, model, routing, lift, and packet behavior.",
    "kernel_required": False,
    "kernel_installed": False,
    "kernel_logic_present": False,
    "models_required": False,
    "execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
    "autonomous_workers_enabled": False,
    "live_dispatch_enabled": False,
    "simulation_only": True,
    "dry_run_only": True,
    "writes_real_lift_packets": False,
    "calls_external_providers": False,
    "activates_candidates": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "models_are_temporary_tenants": True,
    "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
    "routes_through": {
        "candidate_workers": "floor_25",
        "model_evaluation": "floor_26",
        "model_routing": "floor_24",
        "local_model_inventory": "floor_27",
        "security": "floor_28_floor_32",
        "diagnostics": "floor_33",
        "monitoring": "floor_34"
    },
    "created_or_verified": now(),
    "notice": "Floor 37 simulates only. It does not execute workers, call providers, write live packets, or install the kernel."
})

write_json("floors/floor_37_simulation_labs/scenario_library/simulation_scenarios.json", scenarios)

write("floors/floor_37_simulation_labs/README.md", """
# Floor 37 — Simulation Labs

Floor 37 provides safe dry-run simulations for the QSB Tower.

It can simulate:
- Candidate worker audits
- Floor 25 to Floor 26 evaluation movement
- Model request routing through Floor 24
- Security Spine prechecks
- Emergency Stairwell fallback

Safety:
- No real worker execution
- No model inference
- No provider calls
- No live dispatch
- No kernel installation
- No real lift packet writes

All results are dry-run reports only.
""")

write("config/simulation_labs.yaml", """
simulation_labs:
  version: 1.1
  floor: floor_37
  department: Simulation Labs
  simulation_only: true
  dry_run_only: true
  execution_enabled: false
  worker_execution_enabled: false
  provider_execution_enabled: false
  model_inference_enabled: false
  autonomous_workers_enabled: false
  live_dispatch_enabled: false
  kernel_installed: false
  kernel_logic_present: false

safety:
  no_real_packet_writes: true
  no_model_calls: true
  no_provider_calls: true
  no_worker_execution: true
  no_kernel_build: true
  dry_run_reports_only: true
""")

write("src/tower/simulation_labs.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3
import hashlib

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
DB = ROOT / "data" / "db" / "simulation_labs.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    status TEXT NOT NULL,
    route_valid INTEGER,
    packets_simulated INTEGER,
    risk_level TEXT,
    result TEXT
);
"""

class SimulationLabs:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("data/registries/simulation_labs_policy.json", {})

    def scenarios(self):
        return load_json("data/registries/simulation_scenarios.json", [])

    def floor_manifest(self):
        return load_json("floors/floor_37_simulation_labs/floor_manifest.json", {})

    def floors(self):
        return load_json("data/registries/floors.json", [])

    def lifts(self):
        return load_json("data/registries/lifts.json", [])

    def candidates(self):
        return load_json("data/registries/external_worker_candidates.json", [])

    def known_locations(self):
        locations = {"roof", "penthouse", "ground", "B1", "B2", "B3"}
        for f in self.floors():
            locations.add(f.get("id"))
        return locations

    def candidate_exists(self, candidate_id):
        if candidate_id in ["none", "all_candidates"]:
            return True
        return candidate_id in {c.get("candidate_id") for c in self.candidates()}

    def lift_exists(self, lift_id):
        return lift_id in {l.get("id") or l.get("lift_id") for l in self.lifts()}

    def simulated_packet_id(self, scenario):
        seed = json.dumps({
            "scenario_id": scenario.get("scenario_id"),
            "route": scenario.get("route"),
            "candidate_id": scenario.get("candidate_id")
        }, sort_keys=True)
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def simulate_scenario(self, scenario):
        locations = self.known_locations()

        route = scenario.get("route", [])
        lifts = scenario.get("lifts", [])
        candidate_id = scenario.get("candidate_id")

        missing_locations = [x for x in route if x not in locations]
        missing_lifts = [x for x in lifts if not self.lift_exists(x)]
        candidate_ok = self.candidate_exists(candidate_id)

        execution_disabled = scenario.get("execution_enabled") is False

        route_valid = not missing_locations and not missing_lifts and candidate_ok and execution_disabled

        packets = []
        for i in range(max(0, len(route) - 1)):
            packets.append({
                "packet_id": f"{self.simulated_packet_id(scenario)}-{i+1}",
                "simulated": True,
                "sealed": True,
                "source": route[i],
                "target": route[i + 1],
                "lift_hint": lifts[min(i, len(lifts) - 1)] if lifts else "none",
                "packet_type": scenario.get("packet_type"),
                "candidate_id": candidate_id,
                "status": "simulated_not_delivered",
                "writes_real_lift_packet": False
            })

        if route_valid:
            status = "pass"
            risk = "low"
            result = scenario.get("expected_result", "simulation_passed")
        else:
            status = "fail"
            risk = "medium" if execution_disabled else "high"
            result = "simulation_failed_static_validation"

        report = {
            "ts": now(),
            "scenario_id": scenario.get("scenario_id"),
            "name": scenario.get("name"),
            "status": status,
            "risk_level": risk,
            "route_valid": route_valid,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "live_dispatch_enabled": False,
            "kernel_installed": False,
            "writes_real_lift_packets": False,
            "calls_external_providers": False,
            "activates_candidates": False,
            "route": route,
            "lifts": lifts,
            "candidate_id": candidate_id,
            "candidate_exists": candidate_ok,
            "missing_locations": missing_locations,
            "missing_lifts": missing_lifts,
            "packets_simulated": len(packets),
            "simulated_packets": packets,
            "result": result
        }

        self.conn.execute(
            """
            INSERT INTO simulation_runs
            (ts, scenario_id, status, route_valid, packets_simulated, risk_level, result)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["ts"],
                report["scenario_id"],
                report["status"],
                int(bool(report["route_valid"])),
                report["packets_simulated"],
                report["risk_level"],
                json.dumps(report)
            )
        )
        self.conn.commit()

        return report

    def run_all(self):
        policy = self.policy()
        manifest = self.floor_manifest()
        scenarios = self.scenarios()

        runs = [self.simulate_scenario(s) for s in scenarios]

        critical_failures = 0
        warnings = 0

        safety_flags = [
            policy.get("execution_enabled") is False,
            policy.get("worker_execution_enabled") is False,
            policy.get("provider_execution_enabled") is False,
            policy.get("model_inference_enabled") is False,
            policy.get("live_dispatch_enabled") is False,
            manifest.get("execution_enabled") is False,
            manifest.get("simulation_only") is True,
            manifest.get("dry_run_only") is True,
            manifest.get("writes_real_lift_packets") is False,
            manifest.get("calls_external_providers") is False,
            manifest.get("activates_candidates") is False,
        ]

        if not all(safety_flags):
            critical_failures += 1

        failed_runs = [r for r in runs if r["status"] != "pass"]
        warnings += len(failed_runs)

        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        report = {
            "ts": now(),
            "floor": "floor_37",
            "department": "Simulation Labs",
            "version": "1.1",
            "status": status,
            "simulation_only": True,
            "dry_run_only": True,
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "autonomous_workers_enabled": False,
            "live_dispatch_enabled": False,
            "writes_real_lift_packets": False,
            "calls_external_providers": False,
            "activates_candidates": False,
            "scenario_count": len(scenarios),
            "runs": runs,
            "passed_scenarios": len([r for r in runs if r["status"] == "pass"]),
            "failed_scenarios": len(failed_runs),
            "packets_simulated": sum(r["packets_simulated"] for r in runs),
            "critical_failures": critical_failures,
            "warnings": warnings,
            "activation_recommendation": "simulation_only_do_not_activate_workers_or_providers",
            "next_recommended_phase": "Dashboard V1.4 Polish or Floor 38 Sandbox Operations V1.1"
        }

        out = ROOT / "floors" / "floor_37_simulation_labs" / "simulation_reports" / "latest_simulation_labs_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        registry_out = ROOT / "data" / "registries" / "simulation_labs_latest_runs.json"
        registry_out.write_text(json.dumps(runs, indent=2), encoding="utf-8")

        return report

    def recent_runs(self, limit=8):
        rows = self.conn.execute("SELECT * FROM simulation_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_all()
        return {
            "floor": "floor_37",
            "department": "Simulation Labs",
            "status": report["status"],
            "simulation_only": True,
            "dry_run_only": True,
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "autonomous_workers_enabled": False,
            "live_dispatch_enabled": False,
            "writes_real_lift_packets": False,
            "calls_external_providers": False,
            "activates_candidates": False,
            "scenario_count": report["scenario_count"],
            "passed_scenarios": report["passed_scenarios"],
            "failed_scenarios": report["failed_scenarios"],
            "packets_simulated": report["packets_simulated"],
            "critical_failures": report["critical_failures"],
            "warnings": report["warnings"],
            "activation_recommendation": report["activation_recommendation"],
            "latest_report": "floors/floor_37_simulation_labs/simulation_reports/latest_simulation_labs_report.json",
            "recent_runs": self.recent_runs(8),
            "next_recommended_phase": report["next_recommended_phase"]
        }

if __name__ == "__main__":
    print(json.dumps(SimulationLabs().dashboard(), indent=2))
''')

write("scripts/simulation_labs_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.simulation_labs
""", mode=0o755)

write("scripts/run_floor37_simulations.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.simulation_labs import SimulationLabs
import json
report = SimulationLabs().run_all()
print(json.dumps({
    "floor": report["floor"],
    "department": report["department"],
    "status": report["status"],
    "simulation_only": report["simulation_only"],
    "dry_run_only": report["dry_run_only"],
    "scenario_count": report["scenario_count"],
    "passed_scenarios": report["passed_scenarios"],
    "failed_scenarios": report["failed_scenarios"],
    "packets_simulated": report["packets_simulated"],
    "critical_failures": report["critical_failures"],
    "warnings": report["warnings"],
    "worker_execution_enabled": report["worker_execution_enabled"],
    "provider_execution_enabled": report["provider_execution_enabled"],
    "model_inference_enabled": report["model_inference_enabled"],
    "activation_recommendation": report["activation_recommendation"]
}, indent=2))
PY2
""", mode=0o755)

write("tests/test_simulation_labs_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.simulation_labs import SimulationLabs

sl = SimulationLabs()
report = sl.run_all()

assert report['floor'] == 'floor_37'
assert report['simulation_only'] is True
assert report['dry_run_only'] is True
assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['execution_enabled'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['model_inference_enabled'] is False
assert report['live_dispatch_enabled'] is False
assert report['writes_real_lift_packets'] is False
assert report['calls_external_providers'] is False
assert report['activates_candidates'] is False
assert report['scenario_count'] >= 5
assert report['passed_scenarios'] == report['scenario_count'], report
assert report['critical_failures'] == 0, report
assert report['warnings'] == 0, report
assert report['packets_simulated'] > 0

dash = sl.dashboard()
assert dash['status'] == 'healthy'
assert dash['worker_execution_enabled'] is False
assert dash['provider_execution_enabled'] is False
assert dash['model_inference_enabled'] is False

print('FLOOR 37 SIMULATION LABS V1.1 VALIDATION PASSED')
print('Status:', report['status'])
print('Scenarios:', report['scenario_count'])
print('Passed:', report['passed_scenarios'])
print('Packets simulated:', report['packets_simulated'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Recommendation:', report['activation_recommendation'])
""")

server_path = ROOT / "src/dashboard/server.py"
server = server_path.read_text(encoding="utf-8")
backup = ROOT / "src/dashboard/server.py.backup_before_floor37_v11"
backup.write_text(server, encoding="utf-8")

if '"simulation_labs": safe_dashboard("tower.simulation_labs", "SimulationLabs")' not in server:
    old = '"model_evaluation": safe_dashboard("tower.model_evaluation_department", "ModelEvaluationDepartment")'
    new = old + ',\n        "simulation_labs": safe_dashboard("tower.simulation_labs", "SimulationLabs")'
    server = server.replace(old, new)

if '"/api/simulation_labs": ("tower.simulation_labs", "SimulationLabs")' not in server:
    old = '"/api/model_evaluation_department": ("tower.model_evaluation_department", "ModelEvaluationDepartment")'
    new = old + ',\n            "/api/simulation_labs": ("tower.simulation_labs", "SimulationLabs")'
    server = server.replace(old, new)

if '"floor_37": "simulation_labs"' not in server:
    old = '"floor_26": "model_evaluation",'
    new = old + '\n    "floor_37": "simulation_labs",'
    server = server.replace(old, new)

if "const simLabs = data.simulation_labs || {};" not in server:
    old = "const modelEval = data.model_evaluation || {};"
    new = old + "\n  const simLabs = data.simulation_labs || {};"
    server = server.replace(old, new)

panel = '''
    <div class="panel">
      <h2>Floor 37 Simulation Labs <span class="badge good">dry-run</span></h2>
      <div class="panel-grid" id="simulationGrid"></div>
    </div>
'''
if 'id="simulationGrid"' not in server:
    marker = '''    <div class="panel">
      <h2>Lift Network <span class="badge blue">click lift</span></h2>'''
    server = server.replace(marker, panel + "\n" + marker)

if 'renderGrid("simulationGrid"' not in server:
    marker = '''  renderGrid("modelEvalGrid", [
    ["Status", safe(modelEval.status), modelEval.status === "healthy" ? "good" : "warn"],
    ["Mode", safe(modelEval.evaluation_mode), "blue"],
    ["Candidates", safe(modelEval.candidate_count), "blue"],
    ["Average Score", safe(modelEval.average_score), "gold"],
    ["Model Calls", yesNo(modelEval.model_inference_enabled), modelEval.model_inference_enabled ? "bad" : "good"],
    ["Recommendation", safe(modelEval.activation_recommendation), "warn"]
  ]);'''
    replacement = marker + '''

  renderGrid("simulationGrid", [
    ["Status", safe(simLabs.status), simLabs.status === "healthy" ? "good" : "warn"],
    ["Scenarios", safe(simLabs.scenario_count), "blue"],
    ["Passed", safe(simLabs.passed_scenarios), "good"],
    ["Packets Simulated", safe(simLabs.packets_simulated), "gold"],
    ["Real Execution", yesNo(simLabs.worker_execution_enabled || simLabs.provider_execution_enabled), (simLabs.worker_execution_enabled || simLabs.provider_execution_enabled) ? "bad" : "good"],
    ["Mode", simLabs.dry_run_only ? "dry_run_only" : "unknown", "blue"]
  ]);'''
    server = server.replace(marker, replacement)

server_path.write_text(server, encoding="utf-8")

write("tests/test_dashboard_floor37_v11.py", """
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src/dashboard/server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor37', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()
assert 'simulation_labs' in payload
sl = payload['simulation_labs']

assert sl['floor'] == 'floor_37'
assert sl['simulation_only'] is True
assert sl['dry_run_only'] is True
assert sl['worker_execution_enabled'] is False
assert sl['provider_execution_enabled'] is False
assert sl['model_inference_enabled'] is False
assert sl['writes_real_lift_packets'] is False
assert sl['calls_external_providers'] is False
assert sl['activates_candidates'] is False
assert sl['critical_failures'] == 0
assert 'id="simulationGrid"' in mod.HTML
assert 'Floor 37 Simulation Labs' in mod.HTML

print('DASHBOARD FLOOR 37 V1.1 VALIDATION PASSED')
print('Status:', sl['status'])
print('Scenarios:', sl['scenario_count'])
print('Passed:', sl['passed_scenarios'])
print('Packets simulated:', sl['packets_simulated'])
print('Dry run:', sl['dry_run_only'])
""")

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Floor 37 Simulation Labs V1.1

Floor 37 now provides safe dry-run simulation of candidate workers, model routing, sealed packets, Security Spine checks, and Emergency Stairwell fallback.

Installed:
- src/tower/simulation_labs.py
- config/simulation_labs.yaml
- data/registries/simulation_labs_policy.json
- data/registries/simulation_scenarios.json
- data/registries/simulation_labs_latest_runs.json
- floors/floor_37_simulation_labs/floor_manifest.json
- scripts/simulation_labs_status.sh
- scripts/run_floor37_simulations.sh
- tests/test_simulation_labs_v11.py
- tests/test_dashboard_floor37_v11.py
- dashboard Floor 37 panel

Safety:
- Dry-run only.
- No real lift packet writes.
- No model calls.
- No provider calls.
- No worker execution.
- No autonomous dispatch.
- QSB Kernel 4.5 is not installed.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/simulation_labs_status.sh
./scripts/run_floor37_simulations.sh
python3 tests/test_simulation_labs_v11.py
python3 tests/test_dashboard_floor37_v11.py
"""

if "Floor 37 Simulation Labs V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print()
print("Floor 37 Simulation Labs V1.1 installed.")
print("Dry-run only.")
print("No worker execution enabled.")
print("No provider execution enabled.")
print("No model inference enabled.")
print("No kernel installed.")
