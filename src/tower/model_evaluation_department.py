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
