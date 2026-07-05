from pathlib import Path
from datetime import datetime, UTC
import json
import os
import textwrap

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"

def now():
    return datetime.now(UTC).isoformat()

def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

def write_json(rel, obj):
    write(rel, json.dumps(obj, indent=2))

print("Installing Executive Command Spine V1.1: Floors 46-53...")

for folder in [
    "floors/floor_46_executive_support_department/support_records",
    "floors/floor_47_executive_operations_department/operation_records",
    "floors/floor_48_strategic_planning_department/roadmaps",
    "floors/floor_49_resource_management_department/resource_reports",
    "floors/floor_50_building_governance_department/governance_rules",
    "floors/floor_51_executive_council_department/council_records",
    "floors/floor_52_infrastructure_command_department/command_records",
    "floors/floor_53_tower_command_department/handoff_preparation",
    "floors/floor_53_tower_command_department/tower_command_records",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

executive_policy = {
    "version": "1.1",
    "spine_id": "executive_command_spine",
    "floors": [
        "floor_46",
        "floor_47",
        "floor_48",
        "floor_49",
        "floor_50",
        "floor_51",
        "floor_52",
        "floor_53"
    ],
    "role": "upper_tower_command_and_kernel_handoff_preparation_layer",
    "kernel_required": False,
    "kernel_installed": False,
    "models_required": False,
    "execution_enabled": False,
    "command_execution_enabled": False,
    "principle": "Executive floors coordinate readiness, governance, resources, and tower command. They do not contain kernel logic.",
    "notice": "Floor 53 prepares handoff to the Penthouse socket only. QSB Kernel 4.5 is still not installed."
}

executive_floors = [
    {
        "floor_id": "floor_46",
        "number": 46,
        "department": "Executive Support Department",
        "role": "executive_reports_summaries_escalation_support",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 1
    },
    {
        "floor_id": "floor_47",
        "number": 47,
        "department": "Executive Operations Department",
        "role": "upper_tower_operational_coordination",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 2
    },
    {
        "floor_id": "floor_48",
        "number": 48,
        "department": "Strategic Planning Department",
        "role": "roadmap_project_sequence_and_long_range_planning",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 3
    },
    {
        "floor_id": "floor_49",
        "number": 49,
        "department": "Resource Management Department",
        "role": "capacity_resources_workers_models_and_provider_usage_planning",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 4
    },
    {
        "floor_id": "floor_50",
        "number": 50,
        "department": "Building Governance Department",
        "role": "tower_rules_upgrade_governance_registry_policy_version_control",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 5
    },
    {
        "floor_id": "floor_51",
        "number": 51,
        "department": "Executive Council Department",
        "role": "cross_department_review_and_final_recommendation_layer",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 6
    },
    {
        "floor_id": "floor_52",
        "number": 52,
        "department": "Infrastructure Command Department",
        "role": "building_wide_infrastructure_command_visibility",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 7
    },
    {
        "floor_id": "floor_53",
        "number": 53,
        "department": "Tower Command Department",
        "role": "top_level_tower_command_and_kernel_handoff_preparation",
        "status": "online",
        "zone": "ZONE D",
        "execution_enabled": False,
        "command_level": 8,
        "penthouse_handoff_ready": True
    }
]

executive_command_channels = [
    {
        "id": "executive_support_to_operations",
        "source_floor": "floor_46",
        "target_floor": "floor_47",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "operations_to_strategy",
        "source_floor": "floor_47",
        "target_floor": "floor_48",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "strategy_to_resource_management",
        "source_floor": "floor_48",
        "target_floor": "floor_49",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "resource_to_governance",
        "source_floor": "floor_49",
        "target_floor": "floor_50",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "governance_to_council",
        "source_floor": "floor_50",
        "target_floor": "floor_51",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "council_to_infrastructure_command",
        "source_floor": "floor_51",
        "target_floor": "floor_52",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "infrastructure_command_to_tower_command",
        "source_floor": "floor_52",
        "target_floor": "floor_53",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "registered"
    },
    {
        "id": "tower_command_to_penthouse_socket",
        "source_floor": "floor_53",
        "target_floor": "penthouse",
        "lift": "executive_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "handoff_ready"
    }
]

strategic_roadmap = [
    {
        "id": "phase_foundation_complete",
        "floor": "floor_48",
        "phase": "Foundation and Building Infrastructure",
        "status": "complete",
        "notes": "53-floor tower, lifts, registries, dashboard, diagnostics, monitoring, infrastructure services, security spine, expansion planning."
    },
    {
        "id": "phase_executive_spine",
        "floor": "floor_48",
        "phase": "Executive Command Spine",
        "status": "active",
        "notes": "Upper command floors 46-53 are being prepared before future kernel occupancy."
    },
    {
        "id": "phase_lobby_command",
        "floor": "floor_48",
        "phase": "Ground Floor Command Lobby",
        "status": "next_recommended",
        "notes": "Build a proper command reception layer for operating the tower from the lobby."
    },
    {
        "id": "phase_kernel_future",
        "floor": "floor_48",
        "phase": "Future QSB Kernel 4.5 Installation",
        "status": "reserved_future",
        "notes": "Do not build kernel until tower command, lobby command, security enforcement, and acceptance contracts are ready."
    }
]

resource_capacity = {
    "floor": "floor_49",
    "department": "Resource Management Department",
    "kernel_installed": False,
    "models_required": False,
    "execution_enabled": False,
    "tower_capacity": {
        "floors_total": 53,
        "vacant_expansion_floors": 5,
        "lifts": 9,
        "worker_slots_registered": 48,
        "external_provider_sockets": 6,
        "local_models_detected_from_floor_27": "dynamic"
    },
    "resource_policy": "Track resource capacity only. Do not execute providers or models."
}

governance_rules = [
    {
        "id": "kernel_reserved_until_installation",
        "floor": "floor_50",
        "rule": "Penthouse remains reserved for future QSB Kernel 4.5 installation.",
        "status": "active"
    },
    {
        "id": "models_are_tenants",
        "floor": "floor_50",
        "rule": "Models are temporary tenants. The building owns the infrastructure.",
        "status": "active"
    },
    {
        "id": "no_provider_hardwire",
        "floor": "floor_50",
        "rule": "Do not hardwire the tower to Claude, OpenAI, Gemini, DeepSeek, Ollama, or any provider.",
        "status": "active"
    },
    {
        "id": "sealed_lift_packets",
        "floor": "floor_50",
        "rule": "Departments do not communicate directly. Communication travels through sealed lift packets.",
        "status": "active"
    },
    {
        "id": "vacant_floors_serviced",
        "floor": "floor_50",
        "rule": "Vacant floors are fully serviced expansion-ready floors.",
        "status": "active"
    },
    {
        "id": "kernel_not_built_yet",
        "floor": "floor_50",
        "rule": "Do not build QSB Kernel 4.5 yet.",
        "status": "active"
    }
]

council_records = [
    {
        "id": "council_readiness_position",
        "floor": "floor_51",
        "position": "The tower is ready for future kernel socket occupancy but kernel installation remains deferred.",
        "status": "approved_readiness_position"
    },
    {
        "id": "council_next_phase_position",
        "floor": "floor_51",
        "position": "Next recommended phase after Executive Command Spine is Ground Floor Reception and Command Lobby V1.1.",
        "status": "recommended"
    }
]

infrastructure_command_links = [
    {"id": "floor_52_to_diagnostics", "source": "floor_52", "target": "floor_33", "purpose": "diagnostics visibility", "status": "linked"},
    {"id": "floor_52_to_monitoring", "source": "floor_52", "target": "floor_34", "purpose": "monitoring visibility", "status": "linked"},
    {"id": "floor_52_to_infrastructure", "source": "floor_52", "target": "floor_35", "purpose": "infrastructure service visibility", "status": "linked"},
    {"id": "floor_52_to_expansion", "source": "floor_52", "target": "floor_36", "purpose": "expansion capacity visibility", "status": "linked"},
    {"id": "floor_52_to_security", "source": "floor_52", "target": "floor_28_floor_32", "purpose": "security spine visibility", "status": "linked"}
]

tower_command_handoff = {
    "floor": "floor_53",
    "department": "Tower Command Department",
    "handoff_target": "penthouse",
    "handoff_target_status": "reserved_for_future_qsb_kernel_4_5",
    "kernel_installed": False,
    "kernel_logic_present": False,
    "handoff_status": "ready_not_executed",
    "requires": [
        "penthouse_readiness_ready",
        "security_spine_healthy",
        "executive_lift_ready",
        "emergency_stairwell_ready",
        "tower_command_acceptance_report"
    ],
    "execution_enabled": False,
    "notice": "Tower Command prepares handoff to Penthouse socket only. It does not install or run the kernel."
}

write_json("data/registries/executive_command_policy.json", executive_policy)
write_json("data/registries/executive_floors.json", executive_floors)
write_json("data/registries/executive_command_channels.json", executive_command_channels)
write_json("data/registries/strategic_roadmap.json", strategic_roadmap)
write_json("data/registries/resource_capacity.json", resource_capacity)
write_json("data/registries/building_governance_rules.json", governance_rules)
write_json("data/registries/executive_council_records.json", council_records)
write_json("data/registries/infrastructure_command_links.json", infrastructure_command_links)
write_json("data/registries/tower_command_handoff.json", tower_command_handoff)

for floor in executive_floors:
    folder = {
        "floor_46": "floor_46_executive_support_department",
        "floor_47": "floor_47_executive_operations_department",
        "floor_48": "floor_48_strategic_planning_department",
        "floor_49": "floor_49_resource_management_department",
        "floor_50": "floor_50_building_governance_department",
        "floor_51": "floor_51_executive_council_department",
        "floor_52": "floor_52_infrastructure_command_department",
        "floor_53": "floor_53_tower_command_department"
    }[floor["floor_id"]]

    write_json(f"floors/{folder}/floor_manifest.json", {
        "floor_id": floor["floor_id"],
        "department": floor["department"],
        "version": "1.1",
        "role": floor["role"],
        "zone": "ZONE D",
        "kernel_required": False,
        "kernel_installed": False,
        "models_required": False,
        "execution_enabled": False,
        "command_execution_enabled": False,
        "hardwired_providers": False,
        "providers_are_external": True,
        "command_level": floor["command_level"],
        "notice": f"{floor['department']} registered as part of Executive Command Spine V1.1."
    })

write_json("floors/floor_48_strategic_planning_department/roadmaps/strategic_roadmap.json", strategic_roadmap)
write_json("floors/floor_49_resource_management_department/resource_reports/resource_capacity.json", resource_capacity)
write_json("floors/floor_50_building_governance_department/governance_rules/governance_rules.json", governance_rules)
write_json("floors/floor_51_executive_council_department/council_records/council_records.json", council_records)
write_json("floors/floor_52_infrastructure_command_department/command_records/infrastructure_command_links.json", infrastructure_command_links)
write_json("floors/floor_53_tower_command_department/handoff_preparation/tower_command_handoff.json", tower_command_handoff)
write_json("floors/floor_53_tower_command_department/tower_command_records/executive_command_channels.json", executive_command_channels)

write("config/executive_command_spine.yaml", """
executive_command_spine:
  version: 1.1
  floors:
    - floor_46_executive_support_department
    - floor_47_executive_operations_department
    - floor_48_strategic_planning_department
    - floor_49_resource_management_department
    - floor_50_building_governance_department
    - floor_51_executive_council_department
    - floor_52_infrastructure_command_department
    - floor_53_tower_command_department
  execution_enabled: false
  command_execution_enabled: false
  kernel_installed: false
  models_required: false

principle: Executive Command Spine coordinates tower command and future kernel handoff preparation. It does not install, run, or contain the QSB Kernel.
""")

write("src/tower/executive_command.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "executive_command.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_registry(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS executive_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    check_type TEXT,
    target TEXT,
    status TEXT,
    severity TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS executive_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    status TEXT,
    details TEXT
);
"""

class ExecutiveCommand:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_registry("executive_command_policy.json", {})

    def executive_floors(self):
        return load_registry("executive_floors.json", [])

    def channels(self):
        return load_registry("executive_command_channels.json", [])

    def roadmap(self):
        return load_registry("strategic_roadmap.json", [])

    def resource_capacity(self):
        return load_registry("resource_capacity.json", {})

    def governance_rules(self):
        return load_registry("building_governance_rules.json", [])

    def council_records(self):
        return load_registry("executive_council_records.json", [])

    def infrastructure_links(self):
        return load_registry("infrastructure_command_links.json", [])

    def tower_handoff(self):
        return load_registry("tower_command_handoff.json", {})

    def record_check(self, check_type, target, ok, severity="critical", message="", details=None):
        item = {
            "check_type": check_type,
            "target": target,
            "status": "pass" if ok else "fail",
            "severity": severity,
            "message": message,
            "details": details or {}
        }
        self.conn.execute(
            "INSERT INTO executive_checks(ts, check_type, target, status, severity, details) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), check_type, target, item["status"], severity, json.dumps(item))
        )
        self.conn.commit()
        return item

    def record_event(self, event_type, status, details):
        self.conn.execute(
            "INSERT INTO executive_events(ts, event_type, status, details) VALUES (?, ?, ?, ?)",
            (now(), event_type, status, json.dumps(details))
        )
        self.conn.commit()

    def validate_floor_manifests(self):
        folder_map = {
            "floor_46": "floors/floor_46_executive_support_department/floor_manifest.json",
            "floor_47": "floors/floor_47_executive_operations_department/floor_manifest.json",
            "floor_48": "floors/floor_48_strategic_planning_department/floor_manifest.json",
            "floor_49": "floors/floor_49_resource_management_department/floor_manifest.json",
            "floor_50": "floors/floor_50_building_governance_department/floor_manifest.json",
            "floor_51": "floors/floor_51_executive_council_department/floor_manifest.json",
            "floor_52": "floors/floor_52_infrastructure_command_department/floor_manifest.json",
            "floor_53": "floors/floor_53_tower_command_department/floor_manifest.json"
        }

        items = []
        for floor_id, rel in folder_map.items():
            path = ROOT / rel
            ok = path.exists()
            details = {"path": rel}

            if ok:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    details["manifest"] = data
                    ok = (
                        data.get("floor_id") == floor_id
                        and data.get("execution_enabled") is False
                        and data.get("kernel_installed") is False
                    )
                except Exception as e:
                    ok = False
                    details["error"] = str(e)

            items.append(self.record_check(
                "floor_manifest",
                floor_id,
                ok,
                "critical",
                f"{floor_id} executive manifest valid." if ok else f"{floor_id} executive manifest invalid.",
                details
            ))

        return items

    def validate_registry_records(self):
        checks = [
            ("executive_floors", len(self.executive_floors()) == 8, "Executive floors registered."),
            ("executive_command_channels", len(self.channels()) >= 8, "Executive command channels registered."),
            ("strategic_roadmap", len(self.roadmap()) >= 4, "Strategic roadmap registered."),
            ("resource_capacity", bool(self.resource_capacity()), "Resource capacity registry present."),
            ("building_governance_rules", len(self.governance_rules()) >= 6, "Building governance rules registered."),
            ("executive_council_records", len(self.council_records()) >= 2, "Executive council records registered."),
            ("infrastructure_command_links", len(self.infrastructure_links()) >= 5, "Infrastructure command links registered."),
            ("tower_command_handoff", bool(self.tower_handoff()), "Tower command handoff registry present.")
        ]

        return [
            self.record_check("registry", name, ok, "critical", message)
            for name, ok, message in checks
        ]

    def validate_executive_lift_routes(self):
        items = []
        try:
            from tower.lifts import LiftNetwork
            net = LiftNetwork()

            routes = [
                ("floor_46", "floor_47"),
                ("floor_47", "floor_48"),
                ("floor_48", "floor_49"),
                ("floor_49", "floor_50"),
                ("floor_50", "floor_51"),
                ("floor_51", "floor_52"),
                ("floor_52", "floor_53"),
                ("floor_53", "penthouse")
            ]

            for source, target in routes:
                try:
                    lift = net.choose(source, target, "executive_lift")
                    ok = lift.get("id") == "executive_lift"
                    items.append(self.record_check(
                        "executive_lift_route",
                        f"{source}->{target}",
                        ok,
                        "critical",
                        f"Executive route {source}->{target} selected {lift.get('id')}.",
                        {"source": source, "target": target, "selected": lift}
                    ))
                except Exception as e:
                    items.append(self.record_check(
                        "executive_lift_route",
                        f"{source}->{target}",
                        False,
                        "critical",
                        str(e)
                    ))

        except Exception as e:
            items.append(self.record_check("executive_lift_network", "all", False, "critical", str(e)))

        return items

    def validate_handoff_dependencies(self):
        items = []

        try:
            from tower.penthouse_readiness import PenthouseReadiness
            ph = PenthouseReadiness().dashboard()
            ok = (
                ph.get("readiness_status") == "ready_for_future_qsb_kernel_4_5"
                and ph.get("kernel_installed") is False
                and ph.get("kernel_logic_present") is False
            )
            items.append(self.record_check(
                "penthouse_dependency",
                "penthouse_readiness",
                ok,
                "critical",
                f"Penthouse readiness status: {ph.get('readiness_status')}.",
                {"penthouse": ph}
            ))
        except Exception as e:
            items.append(self.record_check("penthouse_dependency", "penthouse_readiness", False, "critical", str(e)))

        try:
            from tower.security_spine import SecuritySpine
            sec = SecuritySpine().dashboard()
            ok = (
                sec.get("status") in ["healthy", "degraded"]
                and sec.get("execution_enabled") is False
                and sec.get("enforcement_enabled") is False
            )
            items.append(self.record_check(
                "security_dependency",
                "security_spine",
                ok,
                "critical",
                f"Security spine status: {sec.get('status')}.",
                {"security": sec}
            ))
        except Exception as e:
            items.append(self.record_check("security_dependency", "security_spine", False, "critical", str(e)))

        try:
            from tower.expansion_planning import ExpansionPlanning
            exp = ExpansionPlanning().dashboard()
            ok = exp.get("expansion_status") in ["healthy", "degraded"]
            items.append(self.record_check(
                "expansion_dependency",
                "floor_36",
                ok,
                "warning",
                f"Expansion planning status: {exp.get('expansion_status')}.",
                {"expansion": exp}
            ))
        except Exception as e:
            items.append(self.record_check("expansion_dependency", "floor_36", False, "warning", str(e)))

        try:
            from tower.infrastructure_services import InfrastructureServices
            infra = InfrastructureServices().dashboard()
            ok = infra.get("infrastructure_status") in ["healthy", "degraded"]
            items.append(self.record_check(
                "infrastructure_dependency",
                "floor_35",
                ok,
                "warning",
                f"Infrastructure status: {infra.get('infrastructure_status')}.",
                {"infrastructure": infra}
            ))
        except Exception as e:
            items.append(self.record_check("infrastructure_dependency", "floor_35", False, "warning", str(e)))

        return items

    def validate_no_kernel_logic(self):
        forbidden = [
            ROOT / "penthouse" / "qsb_kernel_4_5.py",
            ROOT / "penthouse" / "kernel.py",
            ROOT / "src" / "tower" / "qsb_kernel_4_5.py",
            ROOT / "src" / "tower" / "kernel.py"
        ]
        present = [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]

        return [self.record_check(
            "kernel_absence",
            "future_kernel_files",
            not present,
            "critical",
            "Kernel files absent, as required." if not present else "Kernel files found before installation.",
            {"present": present}
        )]

    def executive_summary(self):
        return {
            "ts": now(),
            "floor": "executive_command_spine",
            "department": "Executive Command Spine",
            "version": "1.1",
            "floors": [f.get("floor_id") for f in self.executive_floors()],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "command_execution_enabled": False,
            "roadmap": self.roadmap(),
            "resource_capacity": self.resource_capacity(),
            "governance_rules": self.governance_rules(),
            "council_records": self.council_records(),
            "infrastructure_command_links": self.infrastructure_links(),
            "tower_command_handoff": self.tower_handoff()
        }

    def run_executive_command_check(self):
        items = []
        items.extend(self.validate_floor_manifests())
        items.extend(self.validate_registry_records())
        items.extend(self.validate_executive_lift_routes())
        items.extend(self.validate_handoff_dependencies())
        items.extend(self.validate_no_kernel_logic())

        critical_failures = len([i for i in items if i["status"] == "fail" and i["severity"] == "critical"])
        warnings = len([i for i in items if i["status"] == "fail" and i["severity"] == "warning"])

        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        summary = {
            "ts": now(),
            "spine": "executive_command_spine",
            "version": "1.1",
            "status": status,
            "floors": [f"floor_{i}" for i in range(46, 54)],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "command_execution_enabled": False,
            "checks_run": len(items),
            "critical_failures": critical_failures,
            "warnings": warnings,
            "passed": len([i for i in items if i["status"] == "pass"]),
            "next_recommended_phase": "Ground Floor Reception and Command Lobby V1.1"
        }

        report = {
            "summary": summary,
            "items": items,
            "executive_summary": self.executive_summary()
        }

        out = ROOT / "floors" / "floor_53_tower_command_department" / "tower_command_records" / "latest_executive_command_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        self.record_event("executive_command_check", status, summary)

        return report

    def recent_checks(self, limit=30):
        rows = self.conn.execute("SELECT * FROM executive_checks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM executive_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_executive_command_check()
        summary = report["summary"]
        exec_summary = report["executive_summary"]

        return {
            "database": str(DB),
            "spine": "executive_command_spine",
            "department": "Executive Command Spine",
            "version": "1.1",
            "status": summary["status"],
            "floors": summary["floors"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "command_execution_enabled": False,
            "executive_floors": len(self.executive_floors()),
            "command_channels": len(self.channels()),
            "governance_rules": len(self.governance_rules()),
            "roadmap_items": len(self.roadmap()),
            "resource_capacity": exec_summary["resource_capacity"],
            "tower_command_handoff": exec_summary["tower_command_handoff"],
            "checks_run": summary["checks_run"],
            "critical_failures": summary["critical_failures"],
            "warnings": summary["warnings"],
            "passed": summary["passed"],
            "next_recommended_phase": summary["next_recommended_phase"],
            "latest_report": "floors/floor_53_tower_command_department/tower_command_records/latest_executive_command_report.json",
            "recent_checks": self.recent_checks(10),
            "recent_events": self.recent_events(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(ExecutiveCommand().dashboard(), indent=2))
''')

write("scripts/executive_command_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.executive_command
""")

write("scripts/run_executive_command_check.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.executive_command import ExecutiveCommand
import json
spine = ExecutiveCommand()
report = spine.run_executive_command_check()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_53_tower_command_department/tower_command_records/latest_executive_command_report.json")
PY2
""")

for script in [
    "scripts/executive_command_status.sh",
    "scripts/run_executive_command_check.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_executive_command_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.executive_command import ExecutiveCommand

spine = ExecutiveCommand()
report = spine.run_executive_command_check()
summary = report['summary']

assert summary['spine'] == 'executive_command_spine'
assert summary['kernel_installed'] is False
assert summary['kernel_logic_present'] is False
assert summary['execution_enabled'] is False
assert summary['command_execution_enabled'] is False
assert summary['checks_run'] >= 25
assert summary['critical_failures'] == 0, report
assert summary['status'] in ['healthy', 'degraded']

dash = spine.dashboard()
assert dash['spine'] == 'executive_command_spine'
assert dash['executive_floors'] == 8
assert dash['command_channels'] >= 8
assert dash['governance_rules'] >= 6
assert dash['roadmap_items'] >= 4
assert dash['tower_command_handoff']['kernel_installed'] is False

print('EXECUTIVE COMMAND SPINE V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
print('Next recommended phase:', summary['next_recommended_phase'])
""")

# Patch dashboard server with Executive Command Spine panel and endpoint.
server = ROOT / "src" / "dashboard" / "server.py"
text = server.read_text(encoding="utf-8")

if "from tower.executive_command import ExecutiveCommand" not in text:
    marker = "from tower.expansion_planning import ExpansionPlanning"
    if marker in text:
        text = text.replace(marker, marker + "\nfrom tower.executive_command import ExecutiveCommand")
    else:
        text = text.replace("from tower.penthouse_readiness import PenthouseReadiness", "from tower.penthouse_readiness import PenthouseReadiness\nfrom tower.executive_command import ExecutiveCommand")

if ".executive{" not in text:
    text = text.replace(
        ".expansion{background:#243d1b;border:1px solid #bcff95}",
        ".expansion{background:#243d1b;border:1px solid #bcff95}\n.executive{background:#3d1b31;border:1px solid #ff95df}"
    )

if 'if(f.id==="floor_46" || f.id==="floor_47"' not in text:
    text = text.replace(
        'if(f.id==="floor_36") return "expansion";',
        'if(f.id==="floor_36") return "expansion";\n  if(f.id==="floor_46" || f.id==="floor_47" || f.id==="floor_48" || f.id==="floor_49" || f.id==="floor_50" || f.id==="floor_51" || f.id==="floor_52" || f.id==="floor_53") return "executive";'
    )

if '<div class="panel"><h2>Executive Command Spine</h2><pre id="executive_command_panel"></pre></div>' not in text:
    text = text.replace(
        '<div class="panel"><h2>Penthouse Readiness</h2><pre id="penthouse_panel"></pre></div>',
        '<div class="panel"><h2>Penthouse Readiness</h2><pre id="penthouse_panel"></pre></div>\n<div class="panel"><h2>Executive Command Spine</h2><pre id="executive_command_panel"></pre></div>'
    )

if 'let exec = await (await fetch("/api/executive_command")).json();' not in text:
    text = text.replace(
        'let ph = await (await fetch("/api/penthouse_readiness")).json();',
        'let ph = await (await fetch("/api/penthouse_readiness")).json();\n  let exec = await (await fetch("/api/executive_command")).json();'
    )

if "executive_command_panel.textContent" not in text:
    text = text.replace(
        "security_spine_panel.textContent = JSON.stringify({",
        """executive_command_panel.textContent = JSON.stringify({
    spine:exec.spine,
    department:exec.department,
    status:exec.status,
    floors:exec.floors,
    kernel_installed:exec.kernel_installed,
    kernel_logic_present:exec.kernel_logic_present,
    execution_enabled:exec.execution_enabled,
    command_execution_enabled:exec.command_execution_enabled,
    executive_floors:exec.executive_floors,
    command_channels:exec.command_channels,
    governance_rules:exec.governance_rules,
    roadmap_items:exec.roadmap_items,
    checks_run:exec.checks_run,
    critical_failures:exec.critical_failures,
    warnings:exec.warnings,
    passed:exec.passed,
    tower_command_handoff:exec.tower_command_handoff,
    next_recommended_phase:exec.next_recommended_phase,
    latest_report:exec.latest_report
  },null,2);

  security_spine_panel.textContent = JSON.stringify({"""
    )

if 'if self.path.startswith("/api/executive_command"):' not in text:
    text = text.replace(
        'if self.path.startswith("/api/expansion_planning"):',
        'if self.path.startswith("/api/executive_command"):\n            return self.send_json(ExecutiveCommand().dashboard())\n        if self.path.startswith("/api/expansion_planning"):'
    )

server.write_text(text, encoding="utf-8")

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Executive Command Spine V1.1

Floors 46-53 are now registered as the Executive Command Spine:

- Floor 46 Executive Support
- Floor 47 Executive Operations
- Floor 48 Strategic Planning
- Floor 49 Resource Management
- Floor 50 Building Governance
- Floor 51 Executive Council
- Floor 52 Infrastructure Command
- Floor 53 Tower Command / Kernel Handoff Preparation

This includes:
- Executive floor manifests
- Command channels
- Strategic roadmap registry
- Resource capacity registry
- Building governance rules
- Executive council records
- Infrastructure command links
- Tower Command to Penthouse handoff preparation
- Executive lift route validation
- Dashboard panel

Executive Command Spine V1.1 does not build, install, run, or contain the QSB Kernel.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_executive_command_check.sh
./scripts/executive_command_status.sh
python3 tests/test_executive_command_v11.py
"""

if "Executive Command Spine V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Executive Command Spine V1.1 installed.")
print("Run:")
print("./scripts/run_executive_command_check.sh")
print("./scripts/executive_command_status.sh")
