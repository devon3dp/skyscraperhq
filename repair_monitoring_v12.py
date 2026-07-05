from pathlib import Path
import textwrap

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

print("Repairing Floor 34 Monitoring V1.2...")

monitoring = ROOT / "src" / "tower" / "monitoring_department.py"
server = ROOT / "src" / "dashboard" / "server.py"

text = monitoring.read_text(encoding="utf-8")

start = text.index("    def dashboard_heartbeat(self):")
end = text.index("    def service_uptime(self):")

new_func = r'''
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

'''

text = text[:start] + new_func + text[end:]
monitoring.write_text(text, encoding="utf-8")

# Make dashboard server threaded so future internal endpoint checks do not block.
server_text = server.read_text(encoding="utf-8")
server_text = server_text.replace(
    "from http.server import HTTPServer, BaseHTTPRequestHandler",
    "from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler"
)
server_text = server_text.replace(
    "HTTPServer((\"127.0.0.1\", 8765), Handler).serve_forever()",
    "ThreadingHTTPServer((\"127.0.0.1\", 8765), Handler).serve_forever()"
)
server.write_text(server_text, encoding="utf-8")

test = ROOT / "tests" / "test_monitoring_v12.py"
test.write_text(textwrap.dedent("""
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.monitoring_department import MonitoringDepartment

dept = MonitoringDepartment()
snap = dept.collect_snapshot()

assert snap['floor'] == 'floor_34'
assert snap['department'] == 'Monitoring Department'
assert snap['execution_enabled'] is False
assert snap['dashboard_heartbeat']['status_code'] == 'local_watch'
assert snap['dashboard_heartbeat']['counts']['floors'] == 53
assert snap['dashboard_heartbeat']['counts']['lifts'] >= 6
assert snap['diagnostics_watch']['status'] in ['healthy', 'unknown']

print('MONITORING V1.2 REPAIR VALIDATION PASSED')
print('Monitoring status:', snap['status'])
print('Dashboard online:', snap['dashboard_heartbeat']['online'])
print('PID running:', snap['dashboard_heartbeat']['pid_running'])
print('Registry OK:', snap['dashboard_heartbeat']['registry_ok'])
print('Floors:', snap['dashboard_heartbeat']['counts']['floors'])
print('Lifts:', snap['dashboard_heartbeat']['counts']['lifts'])
""").lstrip(), encoding="utf-8")

print("Monitoring V1.2 repair complete.")
print("Patched:")
print(" - src/tower/monitoring_department.py")
print(" - src/dashboard/server.py")
print(" - tests/test_monitoring_v12.py")
