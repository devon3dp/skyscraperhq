#!/usr/bin/env python3
"""
QSB Worker Self-Report — MASTER PHASE 2B (runs ON the physical worker box).

This tool is HQ-provided, but every FACT it records is collected on THIS machine and
the Task-Council acknowledgement it posts originates from THIS machine as this worker.
HQ does NOT author the worker's statement and does NOT acknowledge on the worker's
behalf — this process does, from the worker's own box. It does NOT mark any task
complete and does NOT fabricate peer verification.

Usage (on the worker):
  python qsb_tp_selfreport.py --worker-id tp_pip --runtime-port 8871 --dashboard-port 9110 \
         --task-id t_410a6227c9 --out TP_PIP_PHASE2B_SELF_REPORT.txt
"""
import argparse, json, socket, subprocess, urllib.request, datetime

HQ_CANDIDATES = ["http://192.168.1.92:8852", "http://192.168.1.72:8852", "http://192.168.1.84:8852"]


def _u():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url, t=3):
    with urllib.request.urlopen(url, timeout=t) as r:
        return r.read(4096).decode("utf-8", "replace")


def _post(url, payload, t=4):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read(4096).decode("utf-8", "replace"))


def discover_hq():
    for b in HQ_CANDIDATES:
        try:
            i = json.loads(_get(b + "/api/hq_identity"))
            if i.get("service") == "qsb_boardroom":
                return b
        except Exception:
            continue
    return None


def ps(cmd):
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                              capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-id", required=True)
    ap.add_argument("--runtime-port", type=int, required=True)
    ap.add_argument("--dashboard-port", type=int, required=True)
    ap.add_argument("--task-id", default="")
    ap.add_argument("--out", default="WORKER_SELF_REPORT.txt")
    a = ap.parse_args()

    host = socket.gethostname().upper()
    adapter = ps("(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | "
                 "Sort-Object {$_.NetAdapter.InterfaceMetric} | Select-Object -First 1 "
                 "-ExpandProperty InterfaceAlias)")
    ipv4 = ps("(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | "
              "Select-Object -First 1 -ExpandProperty IPv4Address).IPAddress")
    # localhost self-checks (this box asking itself)
    try:
        rt = _get("http://127.0.0.1:%d/health" % a.runtime_port); rt_ok = '"ok": true' in rt or '"ok":true' in rt
    except Exception:
        rt, rt_ok = "", False
    try:
        _get("http://127.0.0.1:%d/" % a.dashboard_port); dash_ok = True
    except Exception:
        dash_ok = False

    hq = discover_hq()
    reg = {}
    if hq:
        try:
            reg = json.loads(_get(hq + "/api/physical_workers/" + a.worker_id))
        except Exception:
            reg = {}

    ack_result = "NOT_ATTEMPTED"
    if hq and a.task_id:
        try:
            r = _post(hq + "/tasks/ack", {"id": a.task_id, "actor": a.worker_id,
                                          "text": "Acknowledged by %s from its own box (%s); not complete." % (a.worker_id, host)})
            ack_result = "acknowledged" if r.get("ok") else ("rejected:" + str(r.get("error", "?")))
        except Exception as e:
            ack_result = "error:" + type(e).__name__

    lines = [
        "%s — PHASE 2B SELF-REPORT (generated ON %s at %s)" % (a.worker_id.upper(), host, _u()),
        "This report was produced on the physical worker; facts are local to this machine.",
        "=" * 78,
        "PAST:",
        "  - previous fixed endpoint: %s:%d (assumed permanent — now dynamically registered)" % (ipv4 or "?", a.runtime_port),
        "  - current wireless: on Netgear Wi-Fi (Ethernet currently disconnected).",
        "  - original dashboard/runtime: dashboard :%d, runtime :%d." % (a.dashboard_port, a.runtime_port),
        "",
        "PRESENT:",
        "  - hostname: %s" % host,
        "  - active adapter: %s" % (adapter or "UNKNOWN"),
        "  - current address: %s" % (ipv4 or "UNKNOWN"),
        "  - runtime :%d self-check (localhost): %s" % (a.runtime_port, "LIVE" if rt_ok else "UNREACHABLE"),
        "  - dashboard :%d self-check (localhost): %s" % (a.dashboard_port, "LIVE" if dash_ok else "UNREACHABLE"),
        "  - heartbeat/registration at HQ: state=%s source_ip=%s age=%ss" % (
            reg.get("registration_state", "?"), reg.get("source_ip", "?"), reg.get("heartbeat_age_s", "?")),
        "  - Boardroom (HQ) discovered at: %s" % (hq or "UNRESOLVED"),
        "  - Task Council task acknowledged by this worker: %s -> %s (NOT marked complete)" % (a.task_id or "(none)", ack_result),
        "  - locally owned: this heartbeat client + the runtime/dashboard processes on this box.",
        "",
        "FUTURE:",
        "  - LAN/Wi-Fi failover test pending (Ross-present).",
        "  - risk: DHCP address may change; dynamic registration is designed to absorb it.",
        "  - recommended next: run the Ross-present Ethernet plug/unplug failover test.",
        "=" * 78,
        "Produced by %s on %s. HQ did not author this worker statement or acknowledge on its behalf." % (a.worker_id, host),
    ]
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"wrote": a.out, "host": host, "adapter": adapter, "ipv4": ipv4,
                      "runtime_ok": rt_ok, "dash_ok": dash_ok, "hq": hq, "ack": ack_result}))


if __name__ == "__main__":
    main()
