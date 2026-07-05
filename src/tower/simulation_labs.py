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
