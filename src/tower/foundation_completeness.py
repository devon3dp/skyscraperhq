from pathlib import Path
from datetime import datetime, UTC
import json
import re

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def now():
    return datetime.now(UTC).isoformat()

def load_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

class FoundationCompleteness:
    def __init__(self):
        self.floors = load_json("data/registries/floors.json", [])

    def check_activation_hooks(self):
        items = []
        for floor in self.floors:
            hook = floor.get("activation_hook")
            if not hook:
                items.append({
                    "target": floor.get("id"),
                    "status": "fail",
                    "severity": "warning",
                    "message": "No activation_hook field in floors.json."
                })
                continue

            path = ROOT / hook
            exists = path.exists()
            content = path.read_text(encoding="utf-8") if exists else ""
            blocked = "BLOCKED_SAFE_STUB" in content and "exit 2" in content

            items.append({
                "target": floor.get("id"),
                "hook": hook,
                "exists": exists,
                "blocked_safe_stub": blocked,
                "status": "pass" if exists and blocked else "fail",
                "severity": "critical" if not exists else "warning",
                "message": "Activation hook exists as blocked safe stub." if exists and blocked else "Activation hook missing or unsafe."
            })
        return items

    def check_service_layers(self):
        required = [
            "basement/B3_disaster_recovery/service_manifest.json",
            "basement/B2_vault_archives/service_manifest.json",
            "basement/B1_core_services/service_manifest.json",
            "ground/reception_command_lobby/service_manifest.json",
            "roof/air_llm_cloud/service_manifest.json"
        ]
        items = []
        for rel in required:
            path = ROOT / rel
            ok = path.exists()
            data = load_json(rel, {}) if ok else {}
            safe = (
                ok
                and data.get("kernel_installed") is False
                and data.get("execution_enabled") is False
                and data.get("worker_execution_enabled") is False
            )
            items.append({
                "target": rel,
                "exists": ok,
                "safe": safe,
                "status": "pass" if safe else "fail",
                "severity": "critical",
                "message": "Service layer manifested safely." if safe else "Service layer manifest missing or unsafe."
            })
        return items

    def check_floor_37_40_manifests(self):
        required = {
            "floor_37": "floors/floor_37_simulation_labs/floor_manifest.json",
            "floor_38": "floors/floor_38_sandbox_operations/floor_manifest.json",
            "floor_39": "floors/floor_39_development_labs/floor_manifest.json",
            "floor_40": "floors/floor_40_prototype_systems/floor_manifest.json",
        }
        items = []
        for floor_id, rel in required.items():
            path = ROOT / rel
            ok = path.exists()
            data = load_json(rel, {}) if ok else {}
            safe = (
                ok
                and data.get("floor_id") == floor_id
                and data.get("kernel_installed") is False
                and data.get("execution_enabled") is False
                and data.get("worker_execution_enabled") is False
            )
            items.append({
                "target": floor_id,
                "manifest": rel,
                "exists": ok,
                "safe": safe,
                "status": "pass" if safe else "fail",
                "severity": "critical",
                "message": f"{floor_id} manifest present and safe." if safe else f"{floor_id} manifest missing or unsafe."
            })
        return items

    def check_package_markers(self):
        required = ["src/__init__.py", "src/tower/__init__.py"]
        return [
            {
                "target": rel,
                "exists": (ROOT / rel).exists(),
                "status": "pass" if (ROOT / rel).exists() else "fail",
                "severity": "warning",
                "message": "Package marker exists." if (ROOT / rel).exists() else "Package marker missing."
            }
            for rel in required
        ]

    def run(self):
        items = []
        items.extend(self.check_activation_hooks())
        items.extend(self.check_service_layers())
        items.extend(self.check_floor_37_40_manifests())
        items.extend(self.check_package_markers())

        critical_failures = len([x for x in items if x["status"] == "fail" and x["severity"] == "critical"])
        warnings = len([x for x in items if x["status"] == "fail" and x["severity"] == "warning"])
        passed = len([x for x in items if x["status"] == "pass"])

        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        report = {
            "ts": now(),
            "patch": "foundation_completeness_v13a",
            "status": status,
            "kernel_installed": False,
            "kernel_logic_present": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "checks_run": len(items),
            "passed": passed,
            "critical_failures": critical_failures,
            "warnings": warnings,
            "items": items,
            "next_recommended_phase": "Floor 25 Worker Recruitment and Coordination Department V1.1"
        }

        out = ROOT / "data" / "registries" / "foundation_completeness_latest_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    def dashboard(self):
        report = self.run()
        return {
            "status": report["status"],
            "checks_run": report["checks_run"],
            "passed": report["passed"],
            "critical_failures": report["critical_failures"],
            "warnings": report["warnings"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "next_recommended_phase": report["next_recommended_phase"],
            "latest_report": "data/registries/foundation_completeness_latest_report.json"
        }

if __name__ == "__main__":
    print(json.dumps(FoundationCompleteness().dashboard(), indent=2))
