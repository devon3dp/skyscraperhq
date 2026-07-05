from pathlib import Path
from datetime import datetime, UTC
import json
import os
import re
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
print(" QSB TOWER V1.3A — FOUNDATION COMPLETENESS PATCH")
print(" No kernel. No worker activation. No provider execution.")
print("============================================================")

# ------------------------------------------------------------
# 1. Make source package explicit
# ------------------------------------------------------------
write("src/__init__.py", '"""QSB Tower V1 source package."""\n')
write("src/tower/__init__.py", '"""QSB Tower infrastructure modules."""\n')

# ------------------------------------------------------------
# 2. Create safe activation hook stubs referenced by floors.json
# ------------------------------------------------------------
floors = load_json("data/registries/floors.json", [])
activation_paths = set()

for floor in floors:
    hook = floor.get("activation_hook")
    if hook:
        activation_paths.add(hook)

# Also ensure the canonical zero-padded names exist.
for n in range(1, 54):
    activation_paths.add(f"scripts/activate_floor_{n:02d}.sh")

created_activation_scripts = []

for hook in sorted(activation_paths):
    rel = hook.lstrip("/")
    parts = Path(rel).parts
    if ".." in parts:
        print(f"Skipping unsafe activation path: {hook}")
        continue

    match = re.search(r"activate_floor_(\d+)", rel)
    floor_number = int(match.group(1)) if match else 0
    floor_id = f"floor_{floor_number:02d}" if floor_number else "unknown_floor"

    script = f"""
    #!/usr/bin/env bash
    set -euo pipefail

    ROOT="${{QSB_TOWER_ROOT:-/vaults/nvme0/qsb_tower_v1}}"
    FLOOR_ID="{floor_id}"

    echo "QSB Tower protected activation hook"
    echo "Floor: $FLOOR_ID"
    echo "Status: BLOCKED_SAFE_STUB"
    echo "Execution: disabled"
    echo
    echo "This file exists to satisfy registry activation_hook references."
    echo "It does not activate floors."
    echo "It does not start workers."
    echo "It does not install the QSB Kernel."
    echo
    echo "Future activation must pass:"
    echo "- Floor 36 Expansion Planning approval"
    echo "- Security Spine approval"
    echo "- Manual operator approval"
    echo "- Registry validation"
    echo
    exit 2
    """
    write(rel, script, mode=0o755)
    created_activation_scripts.append(rel)

# ------------------------------------------------------------
# 3. Add manifests to Basement, Ground, and Roof layers
# ------------------------------------------------------------
service_layers = [
    {
        "path": "basement/B3_disaster_recovery",
        "level": "B3",
        "name": "Disaster Recovery",
        "role": "Failover systems, backups, safe-mode startup, recovery logic, and emergency rebuild tools.",
        "lift_access": ["service_lift", "security_lift", "emergency_stairwell"]
    },
    {
        "path": "basement/B2_vault_archives",
        "level": "B2",
        "name": "Vault and Archives",
        "role": "Long-term records, archived events, historical state, protected storage, and locked documents.",
        "lift_access": ["service_lift", "memory_lift", "security_lift", "emergency_stairwell"]
    },
    {
        "path": "basement/B1_core_services",
        "level": "B1",
        "name": "Core Services",
        "role": "SQLite databases, event logs, diagnostics, configuration, registries, and lift control foundations.",
        "lift_access": ["service_lift", "memory_lift", "security_lift", "emergency_stairwell"]
    },
    {
        "path": "ground/reception_command_lobby",
        "level": "G",
        "name": "Reception and Command Lobby",
        "role": "Dashboard entry, user command intake, building directory, session reception, and global overview.",
        "lift_access": ["main_low_rise", "service_lift", "security_lift", "emergency_stairwell"]
    },
    {
        "path": "roof/air_llm_cloud",
        "level": "ROOF",
        "name": "AIR LLM Cloud",
        "role": "External provider visibility layer. Providers remain external tenants and are not hardwired into the building.",
        "lift_access": ["model_lift", "service_lift", "security_lift", "emergency_stairwell"]
    }
]

for layer in service_layers:
    manifest = {
        "id": layer["level"].lower().replace(" ", "_"),
        "level": layer["level"],
        "name": layer["name"],
        "role": layer["role"],
        "status": "online",
        "kernel_required": False,
        "kernel_installed": False,
        "models_required": False,
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "providers_are_external": True,
        "lift_access": layer["lift_access"],
        "created_or_verified": now(),
        "notice": "Infrastructure service layer only. No kernel, workers, or provider execution enabled."
    }

    write_json(f"{layer['path']}/service_manifest.json", manifest)
    write(f"{layer['path']}/README.md", f"""
    # {layer['name']}

    Level: {layer['level']}

    Role:
    {layer['role']}

    Status:
    - Registered as a service layer.
    - Execution is disabled.
    - Worker execution is disabled.
    - Provider execution is disabled.
    - Kernel installation is not present.

    This layer exists so the QSB Tower infrastructure is complete before future workers or the future QSB Kernel 4.5 arrive.
    """)

# ------------------------------------------------------------
# 4. Add manifests for Floors 37–40
# ------------------------------------------------------------
floor_37_40 = [
    {
        "folder": "floor_37_simulation_labs",
        "floor_id": "floor_37",
        "number": 37,
        "department": "Simulation Labs",
        "role": "Sandboxed demonstrations, safe fake workers, model traffic simulation, and non-executing scenario previews.",
        "special_flags": {"simulation_only": True, "live_execution_allowed": False}
    },
    {
        "folder": "floor_38_sandbox_operations",
        "floor_id": "floor_38",
        "number": 38,
        "department": "Sandbox Operations",
        "role": "Isolated test zones, experiment containment, temporary task design, and non-destructive dry-run planning.",
        "special_flags": {"sandbox_only": True, "live_execution_allowed": False}
    },
    {
        "folder": "floor_39_development_labs",
        "floor_id": "floor_39",
        "number": 39,
        "department": "Development Labs",
        "role": "Prototype module design, experimental floor builds, and early service testing plans.",
        "special_flags": {"prototype_design_only": True, "live_execution_allowed": False}
    },
    {
        "folder": "floor_40_prototype_systems",
        "floor_id": "floor_40",
        "number": 40,
        "department": "Prototype Systems",
        "role": "Feature previews, staged upgrades, candidate subsystem preparation, and non-executing prototype review.",
        "special_flags": {"prototype_staging_only": True, "live_execution_allowed": False}
    }
]

for floor in floor_37_40:
    manifest = {
        "floor_id": floor["floor_id"],
        "number": floor["number"],
        "department": floor["department"],
        "version": "1.3A",
        "zone": "ZONE C",
        "status": "online",
        "role": floor["role"],
        "kernel_required": False,
        "kernel_installed": False,
        "models_required": False,
        "execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "hardwired_providers": False,
        "providers_are_external": True,
        "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
        "special_flags": floor["special_flags"],
        "created_or_verified": now(),
        "notice": "Infrastructure manifest only. No live execution or worker activation enabled."
    }

    base = f"floors/{floor['folder']}"
    write_json(f"{base}/floor_manifest.json", manifest)
    write(f"{base}/README.md", f"""
    # {floor['department']}

    Floor: {floor['number']}
    Zone: ZONE C

    Role:
    {floor['role']}

    Safety:
    - execution_enabled: false
    - worker_execution_enabled: false
    - provider_execution_enabled: false
    - kernel_installed: false

    This floor is now structurally manifested but remains non-executing.
    """)

# ------------------------------------------------------------
# 5. Create registry record for the patch
# ------------------------------------------------------------
patch_record = {
    "patch": "foundation_completeness_v13a",
    "version": "1.3A",
    "ts": now(),
    "kernel_installed": False,
    "kernel_logic_present": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "changes": [
        "Added explicit src/__init__.py and src/tower/__init__.py",
        "Created safe blocked activation stubs for floor activation_hook references",
        "Added service manifests and README files for B1, B2, B3, Ground, and Roof",
        "Added floor manifests and README files for Floors 37–40",
        "Added validation module, script, and test"
    ],
    "activation_scripts_created": created_activation_scripts,
    "service_layers_manifested": [x["path"] for x in service_layers],
    "floors_manifested": [x["floor_id"] for x in floor_37_40],
    "notice": "This patch completes structural references only. It does not activate workers, providers, floors, or the QSB Kernel."
}
write_json("data/registries/foundation_completeness_v13a.json", patch_record)

# ------------------------------------------------------------
# 6. Foundation completeness validation module
# ------------------------------------------------------------
write("src/tower/foundation_completeness.py", r'''
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
''')

# ------------------------------------------------------------
# 7. Script and test
# ------------------------------------------------------------
write("scripts/foundation_completeness_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.foundation_completeness
""", mode=0o755)

write("tests/test_foundation_completeness_v13a.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.foundation_completeness import FoundationCompleteness

fc = FoundationCompleteness()
report = fc.run()

assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['checks_run'] >= 60, report
assert report['critical_failures'] == 0, report

dash = fc.dashboard()
assert dash['status'] in ['healthy', 'degraded']
assert dash['critical_failures'] == 0

print('FOUNDATION COMPLETENESS V1.3A VALIDATION PASSED')
print('Status:', report['status'])
print('Checks run:', report['checks_run'])
print('Passed:', report['passed'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Next:', report['next_recommended_phase'])
""")

# ------------------------------------------------------------
# 8. README append
# ------------------------------------------------------------
readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Foundation Completeness Patch V1.3A

This patch resolves pre-worker structural gaps found during the Claude Code read-only audit.

Added:
- Safe blocked activation stubs for floor activation_hook references.
- Service manifests for B1, B2, B3, Ground Reception, and Roof AIR LLM Cloud.
- Floor manifests for Floors 37–40.
- Explicit Python package markers: src/__init__.py and src/tower/__init__.py.
- Foundation completeness validation module, script, and test.

Safety:
- Does not install QSB Kernel 4.5.
- Does not enable workers.
- Does not enable providers.
- Does not activate floors.
- Activation scripts intentionally exit with status 2.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/foundation_completeness_status.sh
python3 tests/test_foundation_completeness_v13a.py

Next recommended phase:
Floor 25 Worker Recruitment and Coordination Department V1.1
"""

if "Foundation Completeness Patch V1.3A" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print()
print("Foundation Completeness Patch V1.3A installed.")
print("Created blocked activation stubs:", len(created_activation_scripts))
print("Manifested service layers:", len(service_layers))
print("Manifested floors 37–40:", len(floor_37_40))
print()
print("Run validation:")
print("export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src")
print("python3 tests/test_foundation_completeness_v13a.py")
print("./scripts/foundation_completeness_status.sh")
