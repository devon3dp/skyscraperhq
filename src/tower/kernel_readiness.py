"""
QSB Tower V1.3 — Kernel Integration Readiness Module

Verifies that the tower infrastructure is fully staged for future QSB Kernel 4.5
installation WITHOUT installing the kernel or enabling any execution.

Final status values:
  NOT_READY_FOR_KERNEL_INTEGRATION
  READY_FOR_KERNEL_DESIGN_ONLY
  READY_FOR_KERNEL_INTEGRATION   (target — all checks pass, kernel not installed)
  READY_FOR_DORMANT_KERNEL_REVIEW (dormant import present, pending compatibility review)
"""

import json
import importlib
import sqlite3
from pathlib import Path
from datetime import datetime, UTC

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"
DB   = ROOT / "data" / "db" / "kernel_readiness.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readiness_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT,
    status     TEXT,
    checks_run INTEGER,
    passed     INTEGER,
    warnings   INTEGER,
    failures   INTEGER,
    summary_json TEXT
);
"""

FORBIDDEN_FILES = [
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "penthouse" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
]


def now():
    return datetime.now(UTC).isoformat()


def load_reg(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def safe_dash(module_name, class_name):
    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        return cls().dashboard()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def chk(name, ok, sev="critical", msg=""):
    return {"name": name, "status": "pass" if ok else "fail",
            "severity": sev, "message": msg}


class KernelReadiness:

    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ── Individual check groups ────────────────────────────────────────

    def check_forbidden_files(self):
        present = [str(f.relative_to(ROOT)) for f in FORBIDDEN_FILES if f.exists()]
        return chk("no_forbidden_kernel_files", not present, "critical",
                   "No kernel logic present." if not present
                   else "FORBIDDEN kernel files detected: " + str(present))

    def check_floor_count(self):
        floors = load_reg("floors.json", [])
        n = len(floors)
        return chk("floor_count_53", n == 53, "critical",
                   f"Floor count: {n} (expected 53).")

    def check_vacant_floors(self):
        floors = load_reg("floors.json", [])
        vacant = [f for f in floors if f.get("vacant")]
        n = len(vacant)
        return chk("vacant_floor_count_5", n == 5, "warning",
                   f"Vacant floor count: {n} (expected 5).")

    def check_lift_count(self):
        lifts = load_reg("lifts.json", [])
        n = len(lifts)
        return chk("lift_count_9", n >= 9, "critical",
                   f"Lift count: {n} (expected >=9).")

    def check_penthouse_socket(self):
        sock = load_reg("kernel_installation_socket.json", {})
        ok = (sock.get("status") == "socket_ready_empty" and
              sock.get("kernel_installed") is False)
        return chk("penthouse_socket_empty_ready", ok, "critical",
                   "Penthouse socket is empty and ready." if ok
                   else "Penthouse socket status unexpected: " + str(sock))

    def check_kernel_not_installed(self):
        sock = load_reg("kernel_installation_socket.json", {})
        ok = sock.get("kernel_installed") is False
        return chk("kernel_not_installed", ok, "critical",
                   "kernel_installed is False." if ok
                   else "kernel_installed is NOT False — stop immediately.")

    def check_safety_flags(self):
        items = []
        checks = [
            ("agent_coordination_policy.json", "live_dispatch_enabled"),
            ("agent_coordination_policy.json", "worker_execution_enabled"),
            ("external_provider_policy.json",  "execution_enabled"),
            ("model_evaluation_policy.json",   "model_inference_enabled"),
        ]
        for fname, key in checks:
            data = load_reg(fname, {})
            if not isinstance(data, dict):
                data = {}
            val = data.get(key, False)
            items.append(chk(
                f"safety_{key}_false",
                not val,
                "critical",
                f"{key} in {fname}: {val} (must be False)."
            ))
        return items

    def check_floor_modules(self):
        modules = [
            ("floor_21_adapter_systems",   "tower.adapter_systems",          "AdapterSystems",          "adapter_count"),
            ("floor_22_integration",       "tower.integration_services",     "IntegrationServices",     "integration_health"),
            ("floor_23_air_llm",           "tower.air_llm_operations",       "AirLLMOperations",        "provider_count"),
            ("floor_24_routing",           "tower.model_routing_department", "ModelRoutingDepartment",  "route_decisions"),
            ("floor_25_agent_coord",       "tower.agent_coordination",       "AgentCoordination",       "status"),
            ("floor_26_model_eval",        "tower.model_evaluation_department","ModelEvaluationDepartment","status"),
            ("floor_27_local_models",      "tower.local_model_operations",   "LocalModelOperations",    "status"),
            ("floor_37_simulation_labs",   "tower.simulation_labs",          "SimulationLabs",          "status"),
            ("floor_38_sandbox_ops",       "tower.sandbox_operations",       "SandboxOperations",       "status"),
        ]
        items = []
        for name, mod, cls, key in modules:
            dash = safe_dash(mod, cls)
            if dash.get("status") == "error":
                items.append(chk(name, False, "warning",
                                 f"{cls} error: {dash.get('error', '?')}"))
            else:
                val = dash.get(key)
                ok = val not in (None, "error")
                items.append(chk(name, ok, "warning",
                                 f"{cls}.{key} = {val}"))
        return items

    def check_openclaw_candidate_only(self):
        oc = load_reg("openclaw_candidate_registry.json", [])
        items = []
        for entry in oc:
            cid = entry.get("candidate_id", "?")
            ok = (entry.get("current_status") == "candidate_only" and
                  not entry.get("execution_enabled", True) and
                  not entry.get("worker_execution_enabled", True))
            items.append(chk(f"openclaw_{cid}_candidate_only", ok, "critical",
                             f"{cid} is candidate_only with execution disabled." if ok
                             else f"{cid} has execution enabled or wrong status."))
        if not oc:
            items.append(chk("openclaw_registry_exists", False, "warning",
                             "openclaw_candidate_registry.json missing or empty."))
        return items

    def check_pixel_agent_candidate_only(self):
        pa = load_reg("pixel_agent_candidate_registry.json", [])
        items = []
        for entry in pa:
            cid = entry.get("candidate_id", "?")
            ok = (entry.get("current_status") == "candidate_only" and
                  not entry.get("execution_enabled", True) and
                  not entry.get("worker_execution_enabled", True))
            items.append(chk(f"pixel_agent_{cid}_candidate_only", ok, "critical",
                             f"{cid} is candidate_only with execution disabled." if ok
                             else f"{cid} has execution enabled or wrong status."))
        if not pa:
            items.append(chk("pixel_agent_registry_exists", False, "warning",
                             "pixel_agent_candidate_registry.json missing or empty."))
        return items

    def check_dormant_kernel_import(self):
        """Check whether the dormant kernel has been imported into the penthouse socket."""
        dormant_dir = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel"
        manifest    = dormant_dir / "import_manifest.json"
        identity    = dormant_dir / "kernel" / "identity.json"
        items = []

        items.append(chk(
            "dormant_import_dir_exists",
            dormant_dir.exists(),
            "warning",
            "Dormant import directory exists at penthouse socket."
        ))
        items.append(chk(
            "dormant_import_manifest_exists",
            manifest.exists(),
            "warning",
            "Dormant import manifest exists."
        ))
        items.append(chk(
            "dormant_identity_readable",
            identity.exists(),
            "warning",
            "Dormant kernel identity.json readable."
        ))

        # Verify forbidden paths still absent
        forbidden_present = [
            str(p) for p in FORBIDDEN_FILES if p.exists()
        ]
        items.append(chk(
            "dormant_import_no_forbidden_files",
            not forbidden_present,
            "critical",
            "No forbidden kernel files created during dormant import." if not forbidden_present
            else "FORBIDDEN files found: " + str(forbidden_present)
        ))

        # Verify dormant manifest says kernel_installed=false
        if manifest.exists():
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
                safety = m.get("safety_flags", {})
                items.append(chk(
                    "dormant_manifest_kernel_installed_false",
                    safety.get("kernel_installed") is False,
                    "critical",
                    "Dormant manifest: kernel_installed is False."
                ))
                items.append(chk(
                    "dormant_manifest_activation_disabled",
                    not safety.get("activation_enabled", True),
                    "critical",
                    "Dormant manifest: activation_enabled is False."
                ))
            except Exception as e:
                items.append(chk("dormant_manifest_parse", False, "warning", str(e)))

        return items

    def check_no_hardwired_providers(self):
        sockets = load_reg("adapter_sockets.json", [])
        hardwired = [s.get("id") for s in sockets if s.get("hardwired") is True]
        return chk("no_hardwired_provider_sockets", not hardwired, "critical",
                   "No provider sockets hardwired." if not hardwired
                   else "Hardwired sockets detected: " + str(hardwired))

    def check_dashboard(self):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "dashboard_server", ROOT / "src" / "dashboard" / "server.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            p = mod.live_payload()
            floors = p.get("status", {}).get("counts", {}).get("floors", 0)
            ok = (floors == 53)
            return [
                chk("dashboard_floor_count_53", ok, "critical",
                    f"Dashboard live_payload floors: {floors}"),
                chk("dashboard_html_towerRows", "towerRows" in mod.HTML, "warning",
                    "towerRows ID present in HTML."),
                chk("dashboard_no_literal_backslash_n",
                    (chr(92) + "n") not in mod.HTML, "critical",
                    "No literal backslash-n corruption in HTML."),
            ]
        except Exception as e:
            return [chk("dashboard_load", False, "warning", f"Dashboard check error: {e}")]

    # ── Full acceptance run ────────────────────────────────────────────

    def _dormant_import_present(self):
        dormant_dir = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel"
        return dormant_dir.exists() and (dormant_dir / "import_manifest.json").exists()

    def run(self):
        items = []
        items.append(self.check_forbidden_files())
        items.append(self.check_kernel_not_installed())
        items.append(self.check_floor_count())
        items.append(self.check_vacant_floors())
        items.append(self.check_lift_count())
        items.append(self.check_penthouse_socket())
        items.extend(self.check_safety_flags())
        items.extend(self.check_floor_modules())
        items.append(self.check_no_hardwired_providers())
        items.extend(self.check_openclaw_candidate_only())
        items.extend(self.check_pixel_agent_candidate_only())
        items.extend(self.check_dormant_kernel_import())
        items.extend(self.check_dashboard())

        critical_failures = sum(
            1 for i in items if i["status"] == "fail" and i["severity"] == "critical")
        warnings = sum(
            1 for i in items if i["status"] == "fail" and i["severity"] == "critical")
        passed = sum(1 for i in items if i["status"] == "pass")

        dormant_imported = self._dormant_import_present()

        if critical_failures > 0:
            readiness = "NOT_READY_FOR_KERNEL_INTEGRATION"
        elif dormant_imported:
            readiness = "READY_FOR_DORMANT_KERNEL_REVIEW"
        elif warnings > 3:
            readiness = "READY_FOR_KERNEL_DESIGN_ONLY"
        else:
            readiness = "READY_FOR_KERNEL_INTEGRATION"

        # Kernel logic is physically present if dormant import completed
        kernel_logic_present = dormant_imported

        summary = {
            "ts": now(),
            "readiness_status": readiness,
            "checks_run": len(items),
            "passed": passed,
            "warnings": warnings,
            "critical_failures": critical_failures,
            "kernel_installed": False,
            "kernel_logic_present": kernel_logic_present,
            "dormant_kernel_imported": dormant_imported,
            "dormant_kernel_activation_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "live_dispatch_enabled": False,
        }

        self.conn.execute(
            "INSERT INTO readiness_runs(ts,status,checks_run,passed,warnings,failures,summary_json)"
            " VALUES (?,?,?,?,?,?,?)",
            (summary["ts"], readiness, len(items), passed, warnings,
             critical_failures, json.dumps(summary))
        )
        self.conn.commit()

        report = {"summary": summary, "items": items}

        out_reg = REG.parent.parent / "data" / "registries" / "kernel_readiness_latest.json"
        out_reg.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        out_report = ROOT / "penthouse" / "kernel_occupancy_acceptance" / "latest_kernel_readiness_report.json"
        out_report.parent.mkdir(parents=True, exist_ok=True)
        out_report.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    def dashboard(self):
        report = self.run()
        s = report["summary"]
        return {
            "module": "kernel_readiness",
            "readiness_status": s["readiness_status"],
            "checks_run": s["checks_run"],
            "passed": s["passed"],
            "warnings": s["warnings"],
            "critical_failures": s["critical_failures"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "live_dispatch_enabled": False,
        }


if __name__ == "__main__":
    print(json.dumps(KernelReadiness().run(), indent=2))
