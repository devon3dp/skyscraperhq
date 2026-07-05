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
