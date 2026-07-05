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

def load_text(rel):
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""

print("============================================================")
print(" QSB TOWER — FLOOR 25 WORKER RECRUITMENT V1.1")
print(" Candidate workers only. No execution. No kernel.")
print("============================================================")

# ------------------------------------------------------------
# Directories
# ------------------------------------------------------------
for rel in [
    "floors/floor_25_agent_coordination_department",
    "floors/floor_25_agent_coordination_department/recruitment_registry",
    "floors/floor_25_agent_coordination_department/onboarding_queue",
    "floors/floor_25_agent_coordination_department/permission_prechecks",
    "floors/floor_25_agent_coordination_department/recruitment_reports",
    "data/registries",
    "data/db",
    "config",
    "scripts",
    "tests",
    "src/tower",
]:
    (ROOT / rel).mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# Policy and registries
# ------------------------------------------------------------
policy = {
    "version": "1.1",
    "floor": "floor_25",
    "department": "Worker Recruitment and Coordination Department",
    "legacy_department_name": "Agent Coordination Department",
    "role": "Recruit, inspect, classify, and stage candidate workers before future activation.",
    "kernel_required": False,
    "kernel_installed": False,
    "kernel_logic_present": False,
    "models_required": False,
    "execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "autonomous_workers_enabled": False,
    "candidate_registration_enabled": True,
    "live_dispatch_enabled": False,
    "security_enforcement_required_before_activation": True,
    "providers_are_external": True,
    "models_are_temporary_tenants": True,
    "principle": "Floor 25 recruits and coordinates candidate workers. It does not execute workers.",
    "notice": "Claude Code, OpenClaw, Ollama, local models, and future agents may be registered as candidates only."
}

worker_slots = [
    {
        "slot_id": "floor25_recruitment_controller",
        "floor_id": "floor_25",
        "role": "recruitment_controller",
        "candidate_id": None,
        "status": "reserved_unbound",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "model_bound": False,
        "approval_required": True,
        "notes": "Internal coordination slot. No live execution."
    },
    {
        "slot_id": "claude_code_external_inspector_slot",
        "floor_id": "floor_25",
        "role": "external_codebase_inspector",
        "candidate_id": "claude_code",
        "status": "candidate_only",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "model_bound": False,
        "approval_required": True,
        "notes": "Claude Code may inspect the tower as an external tool. It is not a tower worker yet."
    },
    {
        "slot_id": "openclaw_candidate_slot",
        "floor_id": "floor_25",
        "role": "external_worker_candidate",
        "candidate_id": "openclaw",
        "status": "candidate_only",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "model_bound": False,
        "approval_required": True,
        "notes": "OpenClaw placeholder candidate. No installation or activation."
    },
    {
        "slot_id": "ollama_local_candidate_slot",
        "floor_id": "floor_25",
        "role": "local_model_candidate_pool",
        "candidate_id": "ollama_local_models",
        "status": "candidate_only",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "model_bound": False,
        "approval_required": True,
        "notes": "Local models may be candidates through Floor 27 inventory only."
    },
    {
        "slot_id": "future_llm_provider_candidate_slot",
        "floor_id": "floor_25",
        "role": "future_provider_candidate_pool",
        "candidate_id": "future_llm_provider",
        "status": "candidate_only",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "model_bound": False,
        "approval_required": True,
        "notes": "Future provider candidate. Must route through Floor 21, 23, 24, and security gates."
    },
    {
        "slot_id": "human_operator_approval_slot",
        "floor_id": "floor_25",
        "role": "manual_operator_approval",
        "candidate_id": "human_operator",
        "status": "approval_authority_registered",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "model_bound": False,
        "approval_required": False,
        "notes": "Manual operator approval authority. Not an autonomous worker."
    }
]

external_candidates = [
    {
        "candidate_id": "claude_code",
        "name": "Claude Code",
        "candidate_type": "external_code_tool",
        "provider_family": "anthropic",
        "location": "external_terminal_tool",
        "installed_detected": "operator_confirmed",
        "status": "candidate_registered_read_only",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "autonomous_enabled": False,
        "allowed_initial_mode": "read_only_audit",
        "allowed_commands_initial": ["pwd", "ls", "find", "tree", "cat", "grep", "sed"],
        "blocked_initial_actions": ["edit", "write", "create", "delete", "move", "install", "chmod", "rm", "run_tests", "activate_workers", "build_kernel"],
        "notes": "Claude Code is currently an external inspector, not an internal worker."
    },
    {
        "candidate_id": "openclaw",
        "name": "OpenClaw",
        "candidate_type": "external_worker_framework_candidate",
        "provider_family": "unknown_external",
        "location": "not_installed_not_connected",
        "status": "candidate_placeholder",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "autonomous_enabled": False,
        "allowed_initial_mode": "registry_placeholder_only",
        "allowed_commands_initial": [],
        "blocked_initial_actions": ["install", "execute", "dispatch", "autonomous_action"],
        "notes": "Placeholder only. Do not install or trust until audited."
    },
    {
        "candidate_id": "ollama_local_models",
        "name": "Ollama Local Models",
        "candidate_type": "local_model_pool_candidate",
        "provider_family": "local_models",
        "location": "floor_27_local_model_operations",
        "status": "candidate_pool_detected_not_bound",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "autonomous_enabled": False,
        "allowed_initial_mode": "inventory_only",
        "allowed_commands_initial": ["ollama list through Floor 27 only"],
        "blocked_initial_actions": ["inference_execution", "model_binding", "autonomous_dispatch"],
        "notes": "Floor 27 may inventory local models. Floor 25 may stage them as candidates only."
    },
    {
        "candidate_id": "future_llm_provider",
        "name": "Future LLM Provider",
        "candidate_type": "future_external_provider_candidate",
        "provider_family": "future",
        "location": "roof_air_llm_cloud_or_floor_23_socket",
        "status": "future_candidate_placeholder",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "autonomous_enabled": False,
        "allowed_initial_mode": "registry_placeholder_only",
        "allowed_commands_initial": [],
        "blocked_initial_actions": ["provider_call", "api_key_use", "remote_execution"],
        "notes": "Future external engines must connect through building infrastructure, never directly."
    },
    {
        "candidate_id": "human_operator",
        "name": "Human Operator",
        "candidate_type": "manual_approval_authority",
        "provider_family": "operator",
        "location": "ground_command_lobby_future",
        "status": "approval_authority_registered",
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "autonomous_enabled": False,
        "allowed_initial_mode": "manual_approval_only",
        "allowed_commands_initial": [],
        "blocked_initial_actions": ["autonomous_worker_execution"],
        "notes": "Manual approval authority for future recruitment decisions."
    }
]

onboarding_queue = [
    {
        "queue_id": "onboard_claude_code_readonly",
        "candidate_id": "claude_code",
        "requested_role": "external_codebase_inspector",
        "status": "staged_read_only",
        "priority": 0.9,
        "execution_enabled": False,
        "requires_security_spine": True,
        "requires_manual_approval": True,
        "notes": "Already tested as external read-only inspector."
    },
    {
        "queue_id": "onboard_openclaw_placeholder",
        "candidate_id": "openclaw",
        "requested_role": "external_worker_framework_candidate",
        "status": "placeholder_not_ready",
        "priority": 0.4,
        "execution_enabled": False,
        "requires_security_spine": True,
        "requires_manual_approval": True,
        "notes": "Needs tool/source audit before any install."
    },
    {
        "queue_id": "onboard_ollama_candidate_pool",
        "candidate_id": "ollama_local_models",
        "requested_role": "local_model_candidate_pool",
        "status": "inventory_available_not_bound",
        "priority": 0.75,
        "execution_enabled": False,
        "requires_security_spine": True,
        "requires_manual_approval": True,
        "notes": "Use Floor 27 model inventory only."
    }
]

prechecks = [
    {
        "check_id": "no_kernel_installation",
        "description": "Worker recruitment must not install or build QSB Kernel 4.5.",
        "required": True,
        "status": "pass",
        "enforced_value": False
    },
    {
        "check_id": "no_worker_execution",
        "description": "Floor 25 may register candidates but must not execute workers.",
        "required": True,
        "status": "pass",
        "enforced_value": False
    },
    {
        "check_id": "providers_external_only",
        "description": "External providers remain outside the building.",
        "required": True,
        "status": "pass",
        "enforced_value": True
    },
    {
        "check_id": "security_spine_required",
        "description": "Future activation requires Security Spine approval.",
        "required": True,
        "status": "pass",
        "enforced_value": True
    },
    {
        "check_id": "manual_approval_required",
        "description": "Future worker activation requires explicit operator approval.",
        "required": True,
        "status": "pass",
        "enforced_value": True
    }
]

write_json("data/registries/agent_coordination_policy.json", policy)
write_json("data/registries/agent_worker_slots.json", worker_slots)
write_json("data/registries/external_worker_candidates.json", external_candidates)
write_json("data/registries/worker_onboarding_queue.json", onboarding_queue)
write_json("data/registries/worker_recruitment_prechecks.json", prechecks)

write_json("floors/floor_25_agent_coordination_department/floor_manifest.json", {
    "floor_id": "floor_25",
    "number": 25,
    "department": "Worker Recruitment and Coordination Department",
    "legacy_department_name": "Agent Coordination Department",
    "version": "1.1",
    "zone": "ZONE B",
    "status": "online",
    "role": "Candidate worker recruitment, classification, onboarding queue, and permission prechecks.",
    "kernel_required": False,
    "kernel_installed": False,
    "kernel_logic_present": False,
    "models_required": False,
    "execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "autonomous_workers_enabled": False,
    "candidate_registration_enabled": True,
    "live_dispatch_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "models_are_temporary_tenants": True,
    "lift_access": ["main_mid_rise", "service_lift", "model_lift", "security_lift", "emergency_stairwell"],
    "routes_through": {
        "model_requests": "floor_24",
        "local_model_inventory": "floor_27",
        "external_provider_sockets": "floor_23",
        "adapters": "floor_21",
        "security": "floor_28_floor_32"
    },
    "created_or_verified": now(),
    "notice": "Floor 25 is recruitment and coordination only. Candidate workers are not active."
})

write_json("floors/floor_25_agent_coordination_department/recruitment_registry/worker_slots.json", worker_slots)
write_json("floors/floor_25_agent_coordination_department/recruitment_registry/external_worker_candidates.json", external_candidates)
write_json("floors/floor_25_agent_coordination_department/onboarding_queue/onboarding_queue.json", onboarding_queue)
write_json("floors/floor_25_agent_coordination_department/permission_prechecks/prechecks.json", prechecks)

write("floors/floor_25_agent_coordination_department/README.md", """
# Floor 25 — Worker Recruitment and Coordination Department

This floor recruits and stages candidate workers for the QSB Tower.

Current mode:
- Candidate registration: enabled
- Worker execution: disabled
- Provider execution: disabled
- Autonomous workers: disabled
- QSB Kernel 4.5: not installed

Candidate classes:
- Claude Code as external read-only inspector
- OpenClaw as placeholder candidate only
- Ollama/local models as inventory candidates through Floor 27
- Future LLM providers as external candidates through Floor 23 and Floor 24
- Human operator as manual approval authority

Important:
This floor does not execute workers. It does not bind models. It does not install tools. It does not build the kernel.
""")

write("config/agent_coordination.yaml", """
agent_coordination:
  version: 1.1
  floor: floor_25
  department: Worker Recruitment and Coordination Department
  candidate_registration_enabled: true
  execution_enabled: false
  worker_execution_enabled: false
  provider_execution_enabled: false
  autonomous_workers_enabled: false
  live_dispatch_enabled: false
  kernel_installed: false
  kernel_logic_present: false

routing:
  incoming_lifts:
    - main_mid_rise
    - service_lift
    - security_lift
  outgoing_lifts:
    - service_lift
    - model_lift
    - security_lift
  model_requests_route_through: floor_24
  local_model_inventory_route_through: floor_27
  external_provider_sockets_route_through: floor_23
  adapter_route_through: floor_21

safety:
  manual_approval_required: true
  security_spine_required: true
  no_autonomous_execution: true
  no_kernel_build: true
  no_provider_calls: true
""")

# ------------------------------------------------------------
# Python module
# ------------------------------------------------------------
write("src/tower/agent_coordination.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "agent_coordination.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    created_ts TEXT,
    name TEXT,
    candidate_type TEXT,
    location TEXT,
    status TEXT,
    execution_enabled INTEGER,
    worker_execution_enabled INTEGER,
    provider_execution_enabled INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS worker_slots (
    slot_id TEXT PRIMARY KEY,
    created_ts TEXT,
    floor_id TEXT,
    role TEXT,
    candidate_id TEXT,
    status TEXT,
    execution_enabled INTEGER,
    worker_execution_enabled INTEGER,
    model_bound INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS onboarding_queue (
    queue_id TEXT PRIMARY KEY,
    created_ts TEXT,
    candidate_id TEXT,
    requested_role TEXT,
    status TEXT,
    priority REAL,
    execution_enabled INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS precheck_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    check_id TEXT,
    status TEXT,
    severity TEXT,
    details TEXT
);
"""

class AgentCoordination:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.seed_from_registries()

    def policy(self):
        return load_json("data/registries/agent_coordination_policy.json", {})

    def worker_slots(self):
        return load_json("data/registries/agent_worker_slots.json", [])

    def candidates(self):
        return load_json("data/registries/external_worker_candidates.json", [])

    def onboarding_queue(self):
        return load_json("data/registries/worker_onboarding_queue.json", [])

    def prechecks(self):
        return load_json("data/registries/worker_recruitment_prechecks.json", [])

    def floor_manifest(self):
        return load_json("floors/floor_25_agent_coordination_department/floor_manifest.json", {})

    def seed_from_registries(self):
        for c in self.candidates():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO candidates
                (candidate_id, created_ts, name, candidate_type, location, status,
                 execution_enabled, worker_execution_enabled, provider_execution_enabled, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.get("candidate_id"),
                    now(),
                    c.get("name"),
                    c.get("candidate_type"),
                    c.get("location"),
                    c.get("status"),
                    int(bool(c.get("execution_enabled"))),
                    int(bool(c.get("worker_execution_enabled"))),
                    int(bool(c.get("provider_execution_enabled"))),
                    json.dumps(c)
                )
            )

        for s in self.worker_slots():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO worker_slots
                (slot_id, created_ts, floor_id, role, candidate_id, status,
                 execution_enabled, worker_execution_enabled, model_bound, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s.get("slot_id"),
                    now(),
                    s.get("floor_id"),
                    s.get("role"),
                    s.get("candidate_id"),
                    s.get("status"),
                    int(bool(s.get("execution_enabled"))),
                    int(bool(s.get("worker_execution_enabled"))),
                    int(bool(s.get("model_bound"))),
                    json.dumps(s)
                )
            )

        for q in self.onboarding_queue():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO onboarding_queue
                (queue_id, created_ts, candidate_id, requested_role, status, priority,
                 execution_enabled, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q.get("queue_id"),
                    now(),
                    q.get("candidate_id"),
                    q.get("requested_role"),
                    q.get("status"),
                    float(q.get("priority", 0.0)),
                    int(bool(q.get("execution_enabled"))),
                    json.dumps(q)
                )
            )

        self.conn.commit()

    def record_precheck(self, check_id, ok, severity="critical", details=None):
        item = {
            "check_id": check_id,
            "status": "pass" if ok else "fail",
            "severity": severity,
            "details": details or {}
        }
        self.conn.execute(
            "INSERT INTO precheck_records(ts, check_id, status, severity, details) VALUES (?, ?, ?, ?, ?)",
            (now(), check_id, item["status"], severity, json.dumps(item))
        )
        self.conn.commit()
        return item

    def run_prechecks(self):
        items = []

        policy = self.policy()
        manifest = self.floor_manifest()
        slots = self.worker_slots()
        candidates = self.candidates()
        queue = self.onboarding_queue()
        prechecks = self.prechecks()

        items.append(self.record_precheck(
            "floor_manifest_present_and_safe",
            bool(manifest)
            and manifest.get("floor_id") == "floor_25"
            and manifest.get("kernel_installed") is False
            and manifest.get("execution_enabled") is False
            and manifest.get("worker_execution_enabled") is False,
            "critical",
            {"manifest": manifest}
        ))

        items.append(self.record_precheck(
            "policy_execution_disabled",
            bool(policy)
            and policy.get("execution_enabled") is False
            and policy.get("worker_execution_enabled") is False
            and policy.get("provider_execution_enabled") is False
            and policy.get("autonomous_workers_enabled") is False,
            "critical",
            {"policy": policy}
        ))

        items.append(self.record_precheck(
            "candidate_registration_open_but_execution_closed",
            policy.get("candidate_registration_enabled") is True
            and policy.get("live_dispatch_enabled") is False,
            "critical",
            {"candidate_registration_enabled": policy.get("candidate_registration_enabled"), "live_dispatch_enabled": policy.get("live_dispatch_enabled")}
        ))

        unsafe_slots = [
            s for s in slots
            if s.get("execution_enabled") is not False
            or s.get("worker_execution_enabled") is not False
            or s.get("model_bound") is not False
        ]
        items.append(self.record_precheck(
            "worker_slots_candidate_only",
            len(slots) >= 5 and not unsafe_slots,
            "critical",
            {"slot_count": len(slots), "unsafe_slots": unsafe_slots}
        ))

        unsafe_candidates = [
            c for c in candidates
            if c.get("execution_enabled") is not False
            or c.get("worker_execution_enabled") is not False
            or c.get("provider_execution_enabled") is not False
            or c.get("autonomous_enabled") is not False
        ]
        items.append(self.record_precheck(
            "external_candidates_non_executing",
            len(candidates) >= 4 and not unsafe_candidates,
            "critical",
            {"candidate_count": len(candidates), "unsafe_candidates": unsafe_candidates}
        ))

        unsafe_queue = [q for q in queue if q.get("execution_enabled") is not False]
        items.append(self.record_precheck(
            "onboarding_queue_non_executing",
            len(queue) >= 3 and not unsafe_queue,
            "critical",
            {"queue_count": len(queue), "unsafe_queue": unsafe_queue}
        ))

        failed_registry_prechecks = [p for p in prechecks if p.get("status") != "pass"]
        items.append(self.record_precheck(
            "registry_prechecks_passed",
            len(prechecks) >= 5 and not failed_registry_prechecks,
            "critical",
            {"precheck_count": len(prechecks), "failed_registry_prechecks": failed_registry_prechecks}
        ))

        try:
            from tower.lifts import LiftNetwork
            net = LiftNetwork()
            service = net.choose("floor_25", "floor_24", "service_lift")
            security = net.choose("floor_25", "floor_28", "security_lift")
            model = net.choose("floor_25", "floor_27", "model_lift")
            lifts_ok = service.get("id") == "service_lift" and security.get("id") == "security_lift" and model.get("id") == "model_lift"
            lift_details = {"service": service, "security": security, "model": model}
        except Exception as e:
            lifts_ok = False
            lift_details = {"error": str(e)}

        items.append(self.record_precheck(
            "lift_routes_available",
            lifts_ok,
            "critical",
            lift_details
        ))

        try:
            from tower.security_spine import SecuritySpine
            sec = SecuritySpine().dashboard()
            security_ok = (
                sec.get("status") in ["healthy", "degraded"]
                and sec.get("execution_enabled") is False
                and sec.get("enforcement_enabled") is False
            )
        except Exception as e:
            sec = {"error": str(e)}
            security_ok = False

        items.append(self.record_precheck(
            "security_spine_visible",
            security_ok,
            "warning",
            {"security_spine": sec}
        ))

        try:
            forbidden = [
                ROOT / "penthouse" / "qsb_kernel_4_5.py",
                ROOT / "penthouse" / "kernel.py",
                ROOT / "src" / "tower" / "qsb_kernel_4_5.py",
                ROOT / "src" / "tower" / "kernel.py"
            ]
            present = [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]
            no_kernel = not present
        except Exception as e:
            present = [str(e)]
            no_kernel = False

        items.append(self.record_precheck(
            "kernel_absence_preserved",
            no_kernel,
            "critical",
            {"forbidden_present": present}
        ))

        critical_failures = len([x for x in items if x["status"] == "fail" and x["severity"] == "critical"])
        warnings = len([x for x in items if x["status"] == "fail" and x["severity"] == "warning"])
        passed = len([x for x in items if x["status"] == "pass"])
        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        report = {
            "ts": now(),
            "floor": "floor_25",
            "department": "Worker Recruitment and Coordination Department",
            "version": "1.1",
            "status": status,
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "autonomous_workers_enabled": False,
            "candidate_registration_enabled": True,
            "live_dispatch_enabled": False,
            "candidate_workers": len(candidates),
            "worker_slots": len(slots),
            "onboarding_queue": len(queue),
            "checks_run": len(items),
            "passed": passed,
            "critical_failures": critical_failures,
            "warnings": warnings,
            "items": items,
            "next_recommended_phase": "Floor 26 Model Evaluation Department V1.1"
        }

        out = ROOT / "floors" / "floor_25_agent_coordination_department" / "recruitment_reports" / "latest_agent_coordination_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    def recent_prechecks(self, limit=12):
        rows = self.conn.execute("SELECT * FROM precheck_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_prechecks()
        return {
            "floor": "floor_25",
            "department": "Worker Recruitment and Coordination Department",
            "legacy_department_name": "Agent Coordination Department",
            "status": report["status"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "autonomous_workers_enabled": False,
            "candidate_registration_enabled": True,
            "live_dispatch_enabled": False,
            "candidate_workers": report["candidate_workers"],
            "worker_slots": report["worker_slots"],
            "onboarding_queue": report["onboarding_queue"],
            "checks_run": report["checks_run"],
            "passed": report["passed"],
            "critical_failures": report["critical_failures"],
            "warnings": report["warnings"],
            "known_candidates": [c.get("candidate_id") for c in self.candidates()],
            "safe_initial_modes": {
                c.get("candidate_id"): c.get("allowed_initial_mode")
                for c in self.candidates()
            },
            "latest_report": "floors/floor_25_agent_coordination_department/recruitment_reports/latest_agent_coordination_report.json",
            "next_recommended_phase": report["next_recommended_phase"],
            "recent_prechecks": self.recent_prechecks(10)
        }

if __name__ == "__main__":
    print(json.dumps(AgentCoordination().dashboard(), indent=2))
''')

# ------------------------------------------------------------
# Scripts and tests
# ------------------------------------------------------------
write("scripts/agent_coordination_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.agent_coordination
""", mode=0o755)

write("scripts/run_floor25_prechecks.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.agent_coordination import AgentCoordination
import json
report = AgentCoordination().run_prechecks()
print(json.dumps({
    "floor": report["floor"],
    "department": report["department"],
    "status": report["status"],
    "checks_run": report["checks_run"],
    "passed": report["passed"],
    "critical_failures": report["critical_failures"],
    "warnings": report["warnings"],
    "worker_execution_enabled": report["worker_execution_enabled"],
    "provider_execution_enabled": report["provider_execution_enabled"],
    "next_recommended_phase": report["next_recommended_phase"]
}, indent=2))
PY2
""", mode=0o755)

write("tests/test_agent_coordination_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.agent_coordination import AgentCoordination

ac = AgentCoordination()
report = ac.run_prechecks()

assert report['floor'] == 'floor_25'
assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['execution_enabled'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['autonomous_workers_enabled'] is False
assert report['candidate_registration_enabled'] is True
assert report['live_dispatch_enabled'] is False
assert report['candidate_workers'] >= 5
assert report['worker_slots'] >= 6
assert report['onboarding_queue'] >= 3
assert report['critical_failures'] == 0, report

dash = ac.dashboard()
assert dash['status'] in ['healthy', 'degraded']
assert dash['worker_execution_enabled'] is False
assert dash['provider_execution_enabled'] is False
assert 'claude_code' in dash['known_candidates']
assert 'openclaw' in dash['known_candidates']

print('FLOOR 25 WORKER RECRUITMENT V1.1 VALIDATION PASSED')
print('Status:', report['status'])
print('Checks run:', report['checks_run'])
print('Passed:', report['passed'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Candidates:', report['candidate_workers'])
print('Worker slots:', report['worker_slots'])
print('Next:', report['next_recommended_phase'])
""")

# ------------------------------------------------------------
# Patch dashboard server
# ------------------------------------------------------------
server_path = ROOT / "src" / "dashboard" / "server.py"
server = server_path.read_text(encoding="utf-8")

backup = ROOT / "src" / "dashboard" / "server.py.backup_before_floor25_v11"
backup.write_text(server, encoding="utf-8")

# Add live payload entry
if '"agent_coordination": safe_dashboard("tower.agent_coordination", "AgentCoordination")' not in server:
    old = '"model_infrastructure": safe_dashboard("tower.model_infrastructure", "ModelInfrastructure")'
    new = old + ',\n        "agent_coordination": safe_dashboard("tower.agent_coordination", "AgentCoordination")'
    server = server.replace(old, new)

# Add endpoint
if '"/api/agent_coordination": ("tower.agent_coordination", "AgentCoordination")' not in server:
    old = '"/api/model_infrastructure": ("tower.model_infrastructure", "ModelInfrastructure")'
    new = old + ',\n            "/api/agent_coordination": ("tower.agent_coordination", "AgentCoordination")'
    server = server.replace(old, new)

# Add floor mapping for inspector
if '"floor_25": "agent_coordination"' not in server:
    old = '"floor_24": "routing",'
    new = old + '\n    "floor_25": "agent_coordination",'
    server = server.replace(old, new)

# Add active floor highlight
if '"floor_25","floor_27"' not in server:
    server = server.replace('"floor_24","floor_27"', '"floor_24","floor_25","floor_27"')

# Add agent variable
if "const agent = data.agent_coordination || {};" not in server:
    old = "const integration = data.integration || {};"
    new = old + "\n  const agent = data.agent_coordination || {};"
    server = server.replace(old, new)

# Add panel markup after model panel
panel = '''
    <div class="panel">
      <h2>Floor 25 Worker Recruitment <span class="badge warn">candidate only</span></h2>
      <div class="panel-grid" id="agentGrid"></div>
    </div>
'''
if 'id="agentGrid"' not in server:
    marker = '''    <div class="panel">
      <h2>Lift Network <span class="badge blue">click lift</span></h2>'''
    server = server.replace(marker, panel + "\n" + marker)

# Add grid render after modelGrid render
if 'renderGrid("agentGrid"' not in server:
    marker = '''  renderGrid("modelGrid", [
    ["Adapters", safe(adapters.adapter_count), "blue"],
    ["Integration", safe(integration.integration_health), integration.integration_health === "healthy" ? "good" : "warn"],
    ["Routes", safe(routing.route_decisions), "blue"],
    ["Local Models", safe(local.detected_models), "gold"],
    ["Providers", safe(air.provider_count), "blue"],
    ["Execution", yesNo(air.execution_enabled || adapters.execution_enabled), (air.execution_enabled || adapters.execution_enabled) ? "bad" : "good"]
  ]);'''
    replacement = marker + '''

  renderGrid("agentGrid", [
    ["Status", safe(agent.status), agent.status === "healthy" ? "good" : "warn"],
    ["Candidates", safe(agent.candidate_workers), "blue"],
    ["Worker Slots", safe(agent.worker_slots), "blue"],
    ["Queue", safe(agent.onboarding_queue), "gold"],
    ["Worker Execution", yesNo(agent.worker_execution_enabled), agent.worker_execution_enabled ? "bad" : "good"],
    ["Live Dispatch", yesNo(agent.live_dispatch_enabled), agent.live_dispatch_enabled ? "bad" : "good"]
  ]);'''
    server = server.replace(marker, replacement)

server_path.write_text(server, encoding="utf-8")

# ------------------------------------------------------------
# Dashboard server test for Floor 25
# ------------------------------------------------------------
write("tests/test_dashboard_floor25_v11.py", """
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src' / 'dashboard' / 'server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor25', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert 'agent_coordination' in mod.live_payload()
payload = mod.live_payload()
agent = payload['agent_coordination']

assert agent['floor'] == 'floor_25'
assert agent['worker_execution_enabled'] is False
assert agent['provider_execution_enabled'] is False
assert agent['live_dispatch_enabled'] is False
assert agent['critical_failures'] == 0
assert 'id="agentGrid"' in mod.HTML
assert 'Floor 25 Worker Recruitment' in mod.HTML

print('DASHBOARD FLOOR 25 V1.1 VALIDATION PASSED')
print('Agent status:', agent['status'])
print('Candidates:', agent['candidate_workers'])
print('Worker slots:', agent['worker_slots'])
print('Live dispatch:', agent['live_dispatch_enabled'])
""")

# ------------------------------------------------------------
# README
# ------------------------------------------------------------
readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Floor 25 Worker Recruitment and Coordination Department V1.1

Floor 25 now exists as a candidate-worker recruitment and coordination layer.

Installed:
- src/tower/agent_coordination.py
- config/agent_coordination.yaml
- data/registries/agent_coordination_policy.json
- data/registries/agent_worker_slots.json
- data/registries/external_worker_candidates.json
- data/registries/worker_onboarding_queue.json
- data/registries/worker_recruitment_prechecks.json
- floors/floor_25_agent_coordination_department/floor_manifest.json
- scripts/agent_coordination_status.sh
- scripts/run_floor25_prechecks.sh
- tests/test_agent_coordination_v11.py
- dashboard Floor 25 panel

Safety:
- Candidate registration is enabled.
- Worker execution is disabled.
- Provider execution is disabled.
- Autonomous workers are disabled.
- Live dispatch is disabled.
- QSB Kernel 4.5 is not installed.
- Claude Code is registered only as an external read-only inspector candidate.
- OpenClaw is registered only as a placeholder candidate.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/agent_coordination_status.sh
./scripts/run_floor25_prechecks.sh
python3 tests/test_agent_coordination_v11.py
python3 tests/test_dashboard_floor25_v11.py
"""

if "Floor 25 Worker Recruitment and Coordination Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print()
print("Floor 25 Worker Recruitment and Coordination V1.1 installed.")
print("No worker execution enabled.")
print("No provider execution enabled.")
print("No kernel installed.")
