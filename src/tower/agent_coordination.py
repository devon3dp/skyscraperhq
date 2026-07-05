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
            model = net.choose("floor_24", "floor_27", "model_lift")
            lifts_ok = service.get("id") == "service_lift" and security.get("id") == "security_lift" and model.get("id") == "model_lift"
            lift_details = {
                "route_architecture": "floor_25 -> floor_24 -> floor_27",
                "floor25_to_router": service,
                "floor24_to_local_models": model,
                "floor25_to_security": security,
                "note": "Floor 25 does not need direct model_lift access. It reaches model systems through Floor 24 routing."
            }
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
