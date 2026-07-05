from pathlib import Path
from datetime import datetime, UTC
import json
import os
import sqlite3
import time
import urllib.request
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "monitoring_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS monitoring_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    status TEXT,
    dashboard_online INTEGER,
    dashboard_pid INTEGER,
    service_uptime_seconds REAL,
    cpu_percent REAL,
    memory_percent REAL,
    root_disk_percent REAL,
    tower_disk_percent REAL,
    lift_traffic_total INTEGER,
    packet_count_recent INTEGER,
    diagnostics_status TEXT,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS monitoring_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    status TEXT,
    details TEXT
);
"""

class MonitoringDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("monitoring_policy.json", {})

    def watch_targets(self):
        return load_json("monitoring_watch_targets.json", [])

    def _optional_psutil(self):
        try:
            import psutil
            return psutil
        except Exception:
            return None

    def system_snapshot(self):
        psutil = self._optional_psutil()

        cpu_percent = None
        memory_percent = None

        if psutil:
            try:
                cpu_percent = psutil.cpu_percent(interval=0.05)
            except Exception:
                cpu_percent = None
            try:
                memory_percent = psutil.virtual_memory().percent
            except Exception:
                memory_percent = None
        else:
            try:
                meminfo = Path("/proc/meminfo").read_text()
                data = {}
                for line in meminfo.splitlines():
                    key, val = line.split(":", 1)
                    data[key] = int(val.strip().split()[0])
                total = data.get("MemTotal")
                available = data.get("MemAvailable")
                if total and available:
                    memory_percent = round(((total - available) / total) * 100, 2)
            except Exception:
                memory_percent = None

        root_usage = shutil.disk_usage("/")
        tower_usage = shutil.disk_usage(str(ROOT))

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "root_disk_percent": round((root_usage.used / root_usage.total) * 100, 2),
            "tower_disk_percent": round((tower_usage.used / tower_usage.total) * 100, 2),
            "tower_free_gb": round(tower_usage.free / (1024 ** 3), 2)
        }


    def dashboard_heartbeat(self):
        """
        V1.2 repair:
        Do not call http://127.0.0.1:8765/api/status from inside the dashboard request.
        The dashboard server can be busy serving /api/monitoring_department, so a self-call can
        falsely mark the dashboard offline. Instead, verify the dashboard PID and registry locally.
        """
        uptime = self.service_uptime()
        pid_running = bool(uptime.get("running"))

        registry_error = None
        counts = {
            "floors": None,
            "vacant": None,
            "lifts": None,
            "workers": None,
            "kernel_installed": False
        }

        try:
            from tower.registry import Registry
            reg = Registry()
            floors = reg.floors()
            lifts = reg.lifts()
            workers = reg.workers()

            counts = {
                "floors": len(floors),
                "vacant": len([f for f in floors if f.get("vacant")]),
                "lifts": len(lifts),
                "workers": len(workers),
                "kernel_installed": False
            }

            registry_ok = counts["floors"] == 53 and counts["lifts"] >= 6
        except Exception as e:
            registry_ok = False
            registry_error = str(e)

        online = bool(pid_running and registry_ok)

        return {
            "online": online,
            "pid_running": pid_running,
            "registry_ok": registry_ok,
            "counts": counts,
            "status_code": "local_watch",
            "kernel_installed": False,
            "message": "Dashboard local heartbeat OK." if online else "Dashboard local heartbeat degraded.",
            "registry_error": registry_error
        }

    def service_uptime(self):
        pid_path = ROOT / "data" / "runtime" / "dashboard.pid"
        if not pid_path.exists():
            return {
                "pid": None,
                "running": False,
                "uptime_seconds": 0,
                "message": "No dashboard.pid file."
            }

        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except Exception as e:
            return {
                "pid": None,
                "running": False,
                "uptime_seconds": 0,
                "message": f"Invalid pid file: {e}"
            }

        running = False
        try:
            os.kill(pid, 0)
            running = True
        except Exception:
            running = False

        uptime = 0
        psutil = self._optional_psutil()
        if running and psutil:
            try:
                uptime = time.time() - psutil.Process(pid).create_time()
            except Exception:
                uptime = 0
        elif running:
            try:
                uptime = time.time() - pid_path.stat().st_mtime
            except Exception:
                uptime = 0

        return {
            "pid": pid,
            "running": running,
            "uptime_seconds": round(uptime, 2),
            "message": "Dashboard process running." if running else "Dashboard process not running."
        }

    def lift_traffic(self):
        try:
            from tower.lifts import LiftNetwork
            states = LiftNetwork().states()
            total = sum(int(x.get("traffic_count", 0) or 0) for x in states)
            active = [x for x in states if int(x.get("traffic_count", 0) or 0) > 0]
            return {
                "ok": True,
                "total_traffic": total,
                "active_lifts": len(active),
                "states": states
            }
        except Exception as e:
            return {
                "ok": False,
                "total_traffic": 0,
                "active_lifts": 0,
                "error": str(e),
                "states": []
            }

    def packet_flow(self):
        try:
            from tower.lifts import LiftNetwork
            packets = LiftNetwork().packets()
            by_lift = {}
            by_status = {}
            for p in packets:
                by_lift[p.get("lift_id")] = by_lift.get(p.get("lift_id"), 0) + 1
                by_status[p.get("status")] = by_status.get(p.get("status"), 0) + 1
            return {
                "ok": True,
                "recent_count": len(packets),
                "by_lift": by_lift,
                "by_status": by_status,
                "recent": packets[:10]
            }
        except Exception as e:
            return {
                "ok": False,
                "recent_count": 0,
                "by_lift": {},
                "by_status": {},
                "error": str(e),
                "recent": []
            }

    def floor_registry_watch(self):
        try:
            from tower.registry import Registry
            reg = Registry()
            floors = reg.floors()
            return {
                "ok": True,
                "floors": len(floors),
                "vacant": len([f for f in floors if f.get("vacant")]),
                "zone_counts": self._zone_counts(floors)
            }
        except Exception as e:
            return {
                "ok": False,
                "floors": 0,
                "vacant": 0,
                "error": str(e)
            }

    def _zone_counts(self, floors):
        out = {}
        for f in floors:
            z = f.get("zone", "unknown")
            out[z] = out.get(z, 0) + 1
        return out

    def provider_socket_watch(self):
        out = {
            "adapter_systems": None,
            "air_llm_operations": None,
            "local_model_operations": None
        }

        try:
            from tower.adapter_systems import AdapterSystems
            a = AdapterSystems().dashboard()
            out["adapter_systems"] = {
                "adapter_count": a.get("adapter_count"),
                "execution_enabled": a.get("execution_enabled"),
                "hardwired_adapters": a.get("hardwired_adapters")
            }
        except Exception as e:
            out["adapter_systems"] = {"error": str(e)}

        try:
            from tower.air_llm_operations import AirLLMOperations
            air = AirLLMOperations().dashboard()
            out["air_llm_operations"] = {
                "provider_count": air.get("provider_count"),
                "socket_count": air.get("socket_count"),
                "execution_enabled": air.get("execution_enabled"),
                "hardwired_providers": air.get("hardwired_providers")
            }
        except Exception as e:
            out["air_llm_operations"] = {"error": str(e)}

        try:
            from tower.local_model_operations import LocalModelOperations
            lm = LocalModelOperations().dashboard()
            out["local_model_operations"] = {
                "detected_models": lm.get("detected_models"),
                "execution_enabled": lm.get("execution_enabled"),
                "hardwired_models": lm.get("hardwired_models")
            }
        except Exception as e:
            out["local_model_operations"] = {"error": str(e)}

        return out

    def diagnostics_watch(self):
        report_path = ROOT / "floors" / "floor_33_diagnostics_department" / "inspection_reports" / "latest_report.json"
        if not report_path.exists():
            return {
                "available": False,
                "status": "unknown",
                "message": "No Floor 33 latest report yet."
            }

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            return {
                "available": True,
                "status": summary.get("status", "unknown"),
                "checks_run": summary.get("checks_run"),
                "critical_failures": summary.get("critical_failures"),
                "warning_failures": summary.get("warning_failures"),
                "ts": summary.get("ts")
            }
        except Exception as e:
            return {
                "available": False,
                "status": "error",
                "message": str(e)
            }

    def record_event(self, event_type, status, details):
        self.conn.execute(
            "INSERT INTO monitoring_events(ts, event_type, status, details) VALUES (?, ?, ?, ?)",
            (now(), event_type, status, json.dumps(details))
        )
        self.conn.commit()

    def collect_snapshot(self):
        system = self.system_snapshot()
        heartbeat = self.dashboard_heartbeat()
        uptime = self.service_uptime()
        lifts = self.lift_traffic()
        packets = self.packet_flow()
        floors = self.floor_registry_watch()
        providers = self.provider_socket_watch()
        diagnostics = self.diagnostics_watch()

        critical_issues = []
        warnings = []

        if not heartbeat.get("online"):
            critical_issues.append("dashboard heartbeat offline")
        if not uptime.get("running"):
            critical_issues.append("dashboard process not running")
        if not floors.get("ok"):
            critical_issues.append("floor registry unavailable")
        if not lifts.get("ok"):
            warnings.append("lift traffic unavailable")
        if not packets.get("ok"):
            warnings.append("packet flow unavailable")
        if diagnostics.get("status") not in ["healthy", "unknown"]:
            warnings.append(f"diagnostics status: {diagnostics.get('status')}")

        status = "healthy" if not critical_issues and not warnings else "degraded" if not critical_issues else "critical"

        summary = {
            "ts": now(),
            "floor": "floor_34",
            "department": "Monitoring Department",
            "version": "1.1",
            "status": status,
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "system": system,
            "dashboard_heartbeat": heartbeat,
            "service_uptime": uptime,
            "lift_traffic": lifts,
            "packet_flow": packets,
            "floor_registry": floors,
            "provider_socket_watch": providers,
            "diagnostics_watch": diagnostics
        }

        self.conn.execute(
            """
            INSERT INTO monitoring_snapshots
            (ts, status, dashboard_online, dashboard_pid, service_uptime_seconds, cpu_percent,
             memory_percent, root_disk_percent, tower_disk_percent, lift_traffic_total,
             packet_count_recent, diagnostics_status, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["ts"],
                status,
                int(bool(heartbeat.get("online"))),
                uptime.get("pid"),
                float(uptime.get("uptime_seconds", 0) or 0),
                system.get("cpu_percent"),
                system.get("memory_percent"),
                system.get("root_disk_percent"),
                system.get("tower_disk_percent"),
                int(lifts.get("total_traffic", 0) or 0),
                int(packets.get("recent_count", 0) or 0),
                diagnostics.get("status"),
                json.dumps(summary)
            )
        )
        self.conn.commit()

        out_path = ROOT / "floors" / "floor_34_monitoring_department" / "live_snapshots" / "latest_snapshot.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return summary

    def recent_snapshots(self, limit=10):
        rows = self.conn.execute("SELECT * FROM monitoring_snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["summary"] = json.loads(item.pop("summary_json"))
            except Exception:
                pass
            out.append(item)
        return out

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM monitoring_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        snap = self.collect_snapshot()
        return {
            "database": str(DB),
            "floor": "floor_34",
            "department": "Monitoring Department",
            "version": "1.1",
            "role": "live_building_watch_layer",
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "monitoring_status": snap["status"],
            "dashboard_online": snap["dashboard_heartbeat"].get("online"),
            "dashboard_pid": snap["service_uptime"].get("pid"),
            "service_uptime_seconds": snap["service_uptime"].get("uptime_seconds"),
            "cpu_percent": snap["system"].get("cpu_percent"),
            "memory_percent": snap["system"].get("memory_percent"),
            "tower_disk_percent": snap["system"].get("tower_disk_percent"),
            "tower_free_gb": snap["system"].get("tower_free_gb"),
            "lift_traffic_total": snap["lift_traffic"].get("total_traffic"),
            "active_lifts": snap["lift_traffic"].get("active_lifts"),
            "packet_count_recent": snap["packet_flow"].get("recent_count"),
            "diagnostics_status": snap["diagnostics_watch"].get("status"),
            "critical_issues": snap["critical_issues"],
            "warnings": snap["warnings"],
            "provider_socket_watch": snap["provider_socket_watch"],
            "recent_snapshots": self.recent_snapshots(5),
            "latest_snapshot": "floors/floor_34_monitoring_department/live_snapshots/latest_snapshot.json",
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(MonitoringDepartment().dashboard(), indent=2))
