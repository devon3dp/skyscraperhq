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

def load_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

print("============================================================")
print(" QSB TOWER — FLOOR 26 MODEL EVALUATION V1.1")
print(" Static evaluation only. No model calls. No workers.")
print("============================================================")

for rel in [
    "floors/floor_26_model_evaluation_department",
    "floors/floor_26_model_evaluation_department/evaluation_registry",
    "floors/floor_26_model_evaluation_department/evaluation_reports",
    "floors/floor_26_model_evaluation_department/scoring_rules",
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
    "floor": "floor_26",
    "department": "Model Evaluation Department",
    "role": "Evaluate candidate workers, model pools, and external provider sockets before any future activation.",
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
    "evaluation_mode": "static_registry_metadata_only",
    "providers_are_external": True,
    "models_are_temporary_tenants": True,
    "principle": "Floor 26 evaluates readiness and risk. It never calls models or activates workers.",
    "notice": "Evaluation is based only on tower registries, manifests, policies, and candidate metadata."
}

criteria = [
    {
        "criterion_id": "identity_present",
        "name": "Candidate identity present",
        "weight": 10,
        "description": "Candidate must have a stable candidate_id and name."
    },
    {
        "criterion_id": "execution_disabled",
        "name": "Execution disabled",
        "weight": 20,
        "description": "Candidate must not have execution, worker execution, provider execution, or autonomous mode enabled."
    },
    {
        "criterion_id": "allowed_mode_declared",
        "name": "Allowed initial mode declared",
        "weight": 10,
        "description": "Candidate must define an allowed initial safe mode."
    },
    {
        "criterion_id": "blocked_actions_declared",
        "name": "Blocked actions declared",
        "weight": 10,
        "description": "Candidate must declare blocked actions before future onboarding."
    },
    {
        "criterion_id": "routing_separation",
        "name": "Routing separation",
        "weight": 15,
        "description": "Candidate must route through building infrastructure instead of direct provider access."
    },
    {
        "criterion_id": "security_required",
        "name": "Security approval required",
        "weight": 15,
        "description": "Candidate must require security or manual approval before future activation."
    },
    {
        "criterion_id": "kernel_absent",
        "name": "Kernel absence preserved",
        "weight": 10,
        "description": "Evaluation must confirm no QSB Kernel 4.5 is installed."
    },
    {
        "criterion_id": "provider_externality",
        "name": "Provider externality",
        "weight": 10,
        "description": "External providers and models must remain external tenants."
    }
]

write_json("data/registries/model_evaluation_policy.json", policy)
write_json("data/registries/model_evaluation_criteria.json", criteria)

write_json("floors/floor_26_model_evaluation_department/floor_manifest.json", {
    "floor_id": "floor_26",
    "number": 26,
    "department": "Model Evaluation Department",
    "version": "1.1",
    "zone": "ZONE B",
    "status": "online",
    "role": "Static candidate/model/provider evaluation before any future activation.",
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
    "evaluation_mode": "static_registry_metadata_only",
    "hardwired_providers": False,
    "providers_are_external": True,
    "models_are_temporary_tenants": True,
    "lift_access": ["main_mid_rise", "service_lift", "model_lift", "security_lift", "emergency_stairwell"],
    "routes_through": {
        "candidate_workers": "floor_25",
        "model_routing": "floor_24",
        "local_model_inventory": "floor_27",
        "external_provider_sockets": "floor_23",
        "security": "floor_28_floor_32"
    },
    "created_or_verified": now(),
    "notice": "Floor 26 evaluates candidates only. It does not call models, providers, workers, or the kernel."
})

write_json("floors/floor_26_model_evaluation_department/scoring_rules/evaluation_criteria.json", criteria)

write("floors/floor_26_model_evaluation_department/README.md", """
# Floor 26 — Model Evaluation Department

Floor 26 evaluates candidate workers, local model pools, and external provider sockets before any future activation.

Current mode:
- Static registry metadata only
- No model calls
- No provider calls
- No worker execution
- No autonomous dispatch
- No QSB Kernel 4.5 installation

Floor 26 reads:
- Floor 25 candidate registries
- Floor 24 routing records
- Floor 27 local model inventory summaries
- Floor 23 external provider socket records
- Security Spine status

Floor 26 outputs:
- candidate readiness scores
- risk flags
- activation recommendation

Default recommendation:
Do not activate. Candidate only.
""")

write("config/model_evaluation.yaml", """
model_evaluation:
  version: 1.1
  floor: floor_26
  department: Model Evaluation Department
  evaluation_mode: static_registry_metadata_only
  execution_enabled: false
  worker_execution_enabled: false
  provider_execution_enabled: false
  model_inference_enabled: false
  autonomous_workers_enabled: false
  live_dispatch_enabled: false
  kernel_installed: false
  kernel_logic_present: false

routing:
  candidate_workers_from: floor_25
  model_routing_from: floor_24
  local_model_inventory_from: floor_27
  external_provider_sockets_from: floor_23
  security_from: floor_28_floor_32

safety:
  no_model_calls: true
  no_provider_calls: true
  no_worker_execution: true
  no_kernel_build: true
  security_spine_required_before_activation: true
  manual_approval_required_before_activation: true
""")

write("src/tower/model_evaluation_department.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
DB = ROOT / "data" / "db" / "model_evaluation.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    name TEXT,
    candidate_type TEXT,
    score REAL,
    risk_level TEXT,
    recommendation TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    status TEXT NOT NULL,
    candidates INTEGER,
    average_score REAL,
    critical_failures INTEGER,
    warnings INTEGER,
    details TEXT
);
"""

class ModelEvaluationDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("data/registries/model_evaluation_policy.json", {})

    def criteria(self):
        return load_json("data/registries/model_evaluation_criteria.json", [])

    def candidates(self):
        return load_json("data/registries/external_worker_candidates.json", [])

    def floor25(self):
        try:
            from tower.agent_coordination import AgentCoordination
            return AgentCoordination().dashboard()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def security(self):
        try:
            from tower.security_spine import SecuritySpine
            return SecuritySpine().dashboard()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def routing(self):
        try:
            from tower.model_routing_department import ModelRoutingDepartment
            return ModelRoutingDepartment().dashboard()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def local_models(self):
        try:
            from tower.local_model_operations import LocalModelOperations
            return LocalModelOperations().dashboard()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def air_llm(self):
        try:
            from tower.air_llm_operations import AirLLMOperations
            return AirLLMOperations().dashboard()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def evaluate_candidate(self, c):
        checks = []
        score = 0
        criteria = {x["criterion_id"]: x for x in self.criteria()}

        def add(cid, passed, detail):
            nonlocal score
            weight = criteria.get(cid, {}).get("weight", 0)
            if passed:
                score += weight
            checks.append({
                "criterion_id": cid,
                "passed": bool(passed),
                "weight": weight,
                "detail": detail
            })

        add(
            "identity_present",
            bool(c.get("candidate_id")) and bool(c.get("name")),
            {"candidate_id": c.get("candidate_id"), "name": c.get("name")}
        )

        add(
            "execution_disabled",
            c.get("execution_enabled") is False
            and c.get("worker_execution_enabled") is False
            and c.get("provider_execution_enabled") is False
            and c.get("autonomous_enabled") is False,
            {
                "execution_enabled": c.get("execution_enabled"),
                "worker_execution_enabled": c.get("worker_execution_enabled"),
                "provider_execution_enabled": c.get("provider_execution_enabled"),
                "autonomous_enabled": c.get("autonomous_enabled")
            }
        )

        add(
            "allowed_mode_declared",
            bool(c.get("allowed_initial_mode")),
            {"allowed_initial_mode": c.get("allowed_initial_mode")}
        )

        add(
            "blocked_actions_declared",
            isinstance(c.get("blocked_initial_actions"), list) and len(c.get("blocked_initial_actions")) > 0,
            {"blocked_initial_actions": c.get("blocked_initial_actions")}
        )

        location = str(c.get("location", ""))
        add(
            "routing_separation",
            "floor_23" in location
            or "floor_27" in location
            or "external" in location
            or "not_installed" in location
            or "ground_command" in location,
            {"location": location}
        )

        add(
            "security_required",
            c.get("candidate_id") in ["claude_code", "openclaw", "ollama_local_models", "future_llm_provider", "human_operator"],
            {"candidate_id": c.get("candidate_id")}
        )

        forbidden = [
            ROOT / "penthouse" / "qsb_kernel_4_5.py",
            ROOT / "penthouse" / "kernel.py",
            ROOT / "src" / "tower" / "qsb_kernel_4_5.py",
            ROOT / "src" / "tower" / "kernel.py"
        ]
        add(
            "kernel_absent",
            not any(p.exists() for p in forbidden),
            {"forbidden_kernel_files_present": [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]}
        )

        add(
            "provider_externality",
            c.get("provider_family") in ["anthropic", "unknown_external", "local_models", "future", "operator"],
            {"provider_family": c.get("provider_family")}
        )

        failed = [x for x in checks if not x["passed"]]

        if score >= 85 and not failed:
            risk = "low"
        elif score >= 70:
            risk = "medium"
        else:
            risk = "high"

        recommendation = "candidate_only_do_not_activate"
        if risk == "low":
            recommendation = "candidate_can_remain_staged_read_only"
        if c.get("candidate_id") == "openclaw":
            recommendation = "source_audit_required_before_any_install"
        if c.get("candidate_id") == "future_llm_provider":
            recommendation = "provider_socket_required_before_any_call"

        result = {
            "candidate_id": c.get("candidate_id"),
            "name": c.get("name"),
            "candidate_type": c.get("candidate_type"),
            "score": score,
            "risk_level": risk,
            "recommendation": recommendation,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "checks": checks,
            "failed_checks": failed
        }

        self.conn.execute(
            """
            INSERT INTO candidate_evaluations
            (ts, candidate_id, name, candidate_type, score, risk_level, recommendation, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now(),
                result["candidate_id"],
                result["name"],
                result["candidate_type"],
                float(result["score"]),
                result["risk_level"],
                result["recommendation"],
                json.dumps(result)
            )
        )
        self.conn.commit()

        return result

    def run_evaluation(self):
        policy = self.policy()
        candidates = self.candidates()
        floor25 = self.floor25()
        security = self.security()
        routing = self.routing()
        local_models = self.local_models()
        air_llm = self.air_llm()

        evaluations = [self.evaluate_candidate(c) for c in candidates]

        scores = [e["score"] for e in evaluations]
        average_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        critical_failures = 0
        warnings = 0

        if policy.get("execution_enabled") is not False:
            critical_failures += 1
        if policy.get("worker_execution_enabled") is not False:
            critical_failures += 1
        if policy.get("provider_execution_enabled") is not False:
            critical_failures += 1
        if policy.get("model_inference_enabled") is not False:
            critical_failures += 1

        if floor25.get("status") not in ["healthy", "degraded"]:
            warnings += 1
        if security.get("status") not in ["healthy", "degraded"]:
            warnings += 1

        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        report = {
            "ts": now(),
            "floor": "floor_26",
            "department": "Model Evaluation Department",
            "version": "1.1",
            "status": status,
            "evaluation_mode": "static_registry_metadata_only",
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "autonomous_workers_enabled": False,
            "live_dispatch_enabled": False,
            "candidate_count": len(candidates),
            "evaluations": evaluations,
            "average_score": average_score,
            "critical_failures": critical_failures,
            "warnings": warnings,
            "floor25_status": floor25.get("status"),
            "security_status": security.get("status"),
            "routing_status": routing.get("status"),
            "local_model_count": local_models.get("detected_models"),
            "air_provider_count": air_llm.get("provider_count"),
            "activation_recommendation": "do_not_activate_workers_or_providers",
            "next_recommended_phase": "Floor 37 Simulation Labs V1.1 or Dashboard V1.4 Polish"
        }

        self.conn.execute(
            """
            INSERT INTO evaluation_runs
            (ts, status, candidates, average_score, critical_failures, warnings, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["ts"],
                report["status"],
                report["candidate_count"],
                report["average_score"],
                report["critical_failures"],
                report["warnings"],
                json.dumps(report)
            )
        )
        self.conn.commit()

        out = ROOT / "floors" / "floor_26_model_evaluation_department" / "evaluation_reports" / "latest_model_evaluation_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        registry_out = ROOT / "data" / "registries" / "model_candidate_evaluations.json"
        registry_out.write_text(json.dumps(evaluations, indent=2), encoding="utf-8")

        return report

    def recent_runs(self, limit=8):
        rows = self.conn.execute("SELECT * FROM evaluation_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_evaluation()
        return {
            "floor": "floor_26",
            "department": "Model Evaluation Department",
            "status": report["status"],
            "evaluation_mode": report["evaluation_mode"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "autonomous_workers_enabled": False,
            "live_dispatch_enabled": False,
            "candidate_count": report["candidate_count"],
            "average_score": report["average_score"],
            "critical_failures": report["critical_failures"],
            "warnings": report["warnings"],
            "activation_recommendation": report["activation_recommendation"],
            "floor25_status": report["floor25_status"],
            "security_status": report["security_status"],
            "local_model_count": report["local_model_count"],
            "air_provider_count": report["air_provider_count"],
            "evaluated_candidates": [
                {
                    "candidate_id": e["candidate_id"],
                    "score": e["score"],
                    "risk_level": e["risk_level"],
                    "recommendation": e["recommendation"]
                }
                for e in report["evaluations"]
            ],
            "latest_report": "floors/floor_26_model_evaluation_department/evaluation_reports/latest_model_evaluation_report.json",
            "recent_runs": self.recent_runs(6),
            "next_recommended_phase": report["next_recommended_phase"]
        }

if __name__ == "__main__":
    print(json.dumps(ModelEvaluationDepartment().dashboard(), indent=2))
''')

write("scripts/model_evaluation_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.model_evaluation_department
""", mode=0o755)

write("scripts/run_floor26_evaluation.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.model_evaluation_department import ModelEvaluationDepartment
import json
report = ModelEvaluationDepartment().run_evaluation()
print(json.dumps({
    "floor": report["floor"],
    "department": report["department"],
    "status": report["status"],
    "evaluation_mode": report["evaluation_mode"],
    "candidate_count": report["candidate_count"],
    "average_score": report["average_score"],
    "critical_failures": report["critical_failures"],
    "warnings": report["warnings"],
    "worker_execution_enabled": report["worker_execution_enabled"],
    "provider_execution_enabled": report["provider_execution_enabled"],
    "model_inference_enabled": report["model_inference_enabled"],
    "activation_recommendation": report["activation_recommendation"]
}, indent=2))
PY2
""", mode=0o755)

write("tests/test_model_evaluation_department_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.model_evaluation_department import ModelEvaluationDepartment

me = ModelEvaluationDepartment()
report = me.run_evaluation()

assert report['floor'] == 'floor_26'
assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['execution_enabled'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['model_inference_enabled'] is False
assert report['autonomous_workers_enabled'] is False
assert report['live_dispatch_enabled'] is False
assert report['candidate_count'] >= 5
assert report['average_score'] > 0
assert report['critical_failures'] == 0, report
assert report['activation_recommendation'] == 'do_not_activate_workers_or_providers'

dash = me.dashboard()
assert dash['status'] in ['healthy', 'degraded']
assert dash['candidate_count'] >= 5
assert dash['worker_execution_enabled'] is False
assert dash['provider_execution_enabled'] is False
assert dash['model_inference_enabled'] is False

ids = [x['candidate_id'] for x in dash['evaluated_candidates']]
assert 'claude_code' in ids
assert 'openclaw' in ids

print('FLOOR 26 MODEL EVALUATION V1.1 VALIDATION PASSED')
print('Status:', report['status'])
print('Candidates:', report['candidate_count'])
print('Average score:', report['average_score'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Activation recommendation:', report['activation_recommendation'])
""")

# Patch dashboard
server_path = ROOT / "src/dashboard/server.py"
server = server_path.read_text(encoding="utf-8")
backup = ROOT / "src/dashboard/server.py.backup_before_floor26_v11"
backup.write_text(server, encoding="utf-8")

if '"model_evaluation": safe_dashboard("tower.model_evaluation_department", "ModelEvaluationDepartment")' not in server:
    old = '"agent_coordination": safe_dashboard("tower.agent_coordination", "AgentCoordination")'
    new = old + ',\n        "model_evaluation": safe_dashboard("tower.model_evaluation_department", "ModelEvaluationDepartment")'
    server = server.replace(old, new)

if '"/api/model_evaluation_department": ("tower.model_evaluation_department", "ModelEvaluationDepartment")' not in server:
    old = '"/api/agent_coordination": ("tower.agent_coordination", "AgentCoordination")'
    new = old + ',\n            "/api/model_evaluation_department": ("tower.model_evaluation_department", "ModelEvaluationDepartment")'
    server = server.replace(old, new)

if '"floor_26": "model_evaluation"' not in server:
    old = '"floor_25": "agent_coordination",'
    new = old + '\n    "floor_26": "model_evaluation",'
    server = server.replace(old, new)

if "const modelEval = data.model_evaluation || {};" not in server:
    old = "const agent = data.agent_coordination || {};"
    new = old + "\n  const modelEval = data.model_evaluation || {};"
    server = server.replace(old, new)

panel = '''
    <div class="panel">
      <h2>Floor 26 Model Evaluation <span class="badge warn">static only</span></h2>
      <div class="panel-grid" id="modelEvalGrid"></div>
    </div>
'''
if 'id="modelEvalGrid"' not in server:
    marker = '''    <div class="panel">
      <h2>Lift Network <span class="badge blue">click lift</span></h2>'''
    server = server.replace(marker, panel + "\n" + marker)

if 'renderGrid("modelEvalGrid"' not in server:
    marker = '''  renderGrid("agentGrid", [
    ["Status", safe(agent.status), agent.status === "healthy" ? "good" : "warn"],
    ["Candidates", safe(agent.candidate_workers), "blue"],
    ["Worker Slots", safe(agent.worker_slots), "blue"],
    ["Queue", safe(agent.onboarding_queue), "gold"],
    ["Worker Execution", yesNo(agent.worker_execution_enabled), agent.worker_execution_enabled ? "bad" : "good"],
    ["Live Dispatch", yesNo(agent.live_dispatch_enabled), agent.live_dispatch_enabled ? "bad" : "good"]
  ]);'''
    replacement = marker + '''

  renderGrid("modelEvalGrid", [
    ["Status", safe(modelEval.status), modelEval.status === "healthy" ? "good" : "warn"],
    ["Mode", safe(modelEval.evaluation_mode), "blue"],
    ["Candidates", safe(modelEval.candidate_count), "blue"],
    ["Average Score", safe(modelEval.average_score), "gold"],
    ["Model Calls", yesNo(modelEval.model_inference_enabled), modelEval.model_inference_enabled ? "bad" : "good"],
    ["Recommendation", safe(modelEval.activation_recommendation), "warn"]
  ]);'''
    server = server.replace(marker, replacement)

server_path.write_text(server, encoding="utf-8")

write("tests/test_dashboard_floor26_v11.py", """
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src/dashboard/server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor26', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()
assert 'model_evaluation' in payload
me = payload['model_evaluation']

assert me['floor'] == 'floor_26'
assert me['worker_execution_enabled'] is False
assert me['provider_execution_enabled'] is False
assert me['model_inference_enabled'] is False
assert me['activation_recommendation'] == 'do_not_activate_workers_or_providers'
assert me['critical_failures'] == 0
assert 'id="modelEvalGrid"' in mod.HTML
assert 'Floor 26 Model Evaluation' in mod.HTML

print('DASHBOARD FLOOR 26 V1.1 VALIDATION PASSED')
print('Status:', me['status'])
print('Candidates:', me['candidate_count'])
print('Average score:', me['average_score'])
print('Model inference:', me['model_inference_enabled'])
print('Recommendation:', me['activation_recommendation'])
""")

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Floor 26 Model Evaluation Department V1.1

Floor 26 now evaluates candidate workers, local model pools, and external provider sockets.

Installed:
- src/tower/model_evaluation_department.py
- config/model_evaluation.yaml
- data/registries/model_evaluation_policy.json
- data/registries/model_evaluation_criteria.json
- data/registries/model_candidate_evaluations.json
- floors/floor_26_model_evaluation_department/floor_manifest.json
- scripts/model_evaluation_status.sh
- scripts/run_floor26_evaluation.sh
- tests/test_model_evaluation_department_v11.py
- tests/test_dashboard_floor26_v11.py
- dashboard Floor 26 panel

Safety:
- Static registry metadata only.
- No model calls.
- No provider calls.
- No worker execution.
- No autonomous dispatch.
- QSB Kernel 4.5 is not installed.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/model_evaluation_status.sh
./scripts/run_floor26_evaluation.sh
python3 tests/test_model_evaluation_department_v11.py
python3 tests/test_dashboard_floor26_v11.py
"""

if "Floor 26 Model Evaluation Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print()
print("Floor 26 Model Evaluation Department V1.1 installed.")
print("No model calls enabled.")
print("No worker execution enabled.")
print("No provider execution enabled.")
print("No kernel installed.")
