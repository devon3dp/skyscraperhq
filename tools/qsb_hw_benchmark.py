#!/usr/bin/env python3
"""qsb_hw_benchmark.py — continuous hardware stats collector.

Samples CPU / GPU / RAM / temps every 60s, writes a jsonl trail Ross
can grep. Also surfaces "headroom" so the build_forward loop can scale
its parallel agent count.

Run as systemd-user timer or just `--watch`.
"""
from __future__ import annotations
import argparse, datetime, json, os, pathlib, re, shutil, subprocess, sys, time

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
LOG = ROOT / "data/registries/qsb_hw_stats.jsonl"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def _cpu() -> dict:
    # load average + util via /proc
    out = {"load_1m":0.0, "load_5m":0.0, "util_pct":0.0}
    try:
        with open("/proc/loadavg") as f:
            la = f.read().split()
            out["load_1m"] = float(la[0]); out["load_5m"] = float(la[1])
    except Exception: pass
    # cpu util via /proc/stat delta
    def _read_stat() -> tuple[int,int]:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("cpu "):
                    p = line.split()
                    idle = int(p[4]) + int(p[5])
                    total = sum(int(x) for x in p[1:8])
                    return idle, total
        return 0, 0
    a1, b1 = _read_stat()
    time.sleep(0.5)
    a2, b2 = _read_stat()
    didle = a2 - a1; dtot = b2 - b1
    out["util_pct"] = round(100 * (1.0 - (didle / dtot if dtot else 1.0)), 1)
    return out


def _ram() -> dict:
    out = {"total_gb":0.0, "used_gb":0.0, "free_gb":0.0, "pct_used":0.0}
    try:
        with open("/proc/meminfo") as f:
            mi = {}
            for line in f:
                k, _, v = line.partition(":")
                mi[k.strip()] = int(v.strip().split()[0])  # kB
            tot = mi.get("MemTotal", 0) / 1024 / 1024
            avail = mi.get("MemAvailable", 0) / 1024 / 1024
            used = tot - avail
            out["total_gb"] = round(tot, 1)
            out["used_gb"] = round(used, 1)
            out["free_gb"] = round(avail, 1)
            out["pct_used"] = round(100 * used / tot, 1) if tot else 0.0
    except Exception: pass
    return out


def _gpu() -> dict:
    out = {"name":"?", "vram_total_mb":0, "vram_used_mb":0, "util_pct":0, "temp_c":0}
    if not shutil.which("nvidia-smi"): return out
    try:
        q = "name,memory.total,memory.used,utilization.gpu,temperature.gpu"
        r = subprocess.run(["nvidia-smi", "--query-gpu=" + q, "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=4)
        parts = [p.strip() for p in r.stdout.strip().split(",")]
        if len(parts) >= 5:
            out["name"] = parts[0]
            out["vram_total_mb"] = int(parts[1])
            out["vram_used_mb"]  = int(parts[2])
            out["util_pct"] = int(parts[3])
            out["temp_c"] = int(parts[4])
    except Exception: pass
    return out


def _cpu_temp() -> dict:
    out = {"package_c": None, "tctl_c": None}
    # Try lm-sensors first
    if shutil.which("sensors"):
        try:
            r = subprocess.run(["sensors"], capture_output=True, text=True, timeout=3)
            # AMD Ryzen typically prints Tctl + Tdie
            for line in r.stdout.splitlines():
                m = re.search(r"Tctl:.*?\+([\d.]+).*?C", line)
                if m: out["tctl_c"] = float(m.group(1))
                m = re.search(r"Package id 0:.*?\+([\d.]+).*?C", line)
                if m: out["package_c"] = float(m.group(1))
        except Exception: pass
    # /sys/class/thermal fallback
    for zone in pathlib.Path("/sys/class/thermal").glob("thermal_zone*"):
        try:
            t = int((zone/"temp").read_text()) / 1000.0
            tname = (zone/"type").read_text().strip()
            if "k10temp" in tname or "Tctl" in tname:
                out["tctl_c"] = round(t, 1); break
        except Exception: pass
    return out


def _ollama_models() -> dict:
    out = {"loaded": []}
    try:
        r = subprocess.run(["curl","-s","http://127.0.0.1:11434/api/ps"], capture_output=True, text=True, timeout=3)
        d = json.loads(r.stdout or "{}")
        out["loaded"] = [m.get("name") for m in d.get("models",[])]
    except Exception: pass
    return out


def sample() -> dict:
    return {
        "ts": now_iso(),
        "cpu": _cpu(),
        "ram": _ram(),
        "gpu": _gpu(),
        "cpu_temp": _cpu_temp(),
        "ollama": _ollama_models(),
    }


def headroom_advice(s: dict) -> dict:
    """How many parallel agents the system should run right now."""
    cpu_free = max(0, 100 - s["cpu"]["util_pct"])
    ram_free_pct = max(0, 100 - s["ram"]["pct_used"])
    gpu_free_pct = max(0, 100 - s["gpu"]["util_pct"])
    # Base 3 parallel; bump up if everything is cool, down if hot
    rec = 3
    if cpu_free > 50 and ram_free_pct > 50: rec = 6
    if cpu_free > 75 and ram_free_pct > 70 and gpu_free_pct > 60: rec = 8
    # Safety: if any temp is high, drop back
    temp_c = s["cpu_temp"].get("tctl_c") or s["cpu_temp"].get("package_c") or 0
    if temp_c and temp_c > 85: rec = max(2, rec - 4)
    if s["gpu"]["temp_c"] > 80: rec = max(2, rec - 2)
    return {"parallel_agents_recommended": rec,
            "cpu_free_pct": cpu_free, "ram_free_pct": ram_free_pct,
            "gpu_free_pct": gpu_free_pct, "cpu_temp_c": temp_c, "gpu_temp_c": s["gpu"]["temp_c"]}


def cmd_once(quiet: bool = False):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    s = sample(); h = headroom_advice(s); s["headroom"] = h
    with LOG.open("a") as f: f.write(json.dumps(s) + "\n")
    # stamp F47 only occasionally (every 5th sample) to avoid spam
    if int(time.time()) % 300 < 60:
        with F47.open("a") as f:
            f.write(json.dumps({
                "ts": s["ts"], "kind":"hw_sample",
                "operator":"hw_benchmark",
                "summary": f"cpu {s['cpu']['util_pct']}%  ram {s['ram']['pct_used']}%  gpu {s['gpu']['util_pct']}% @ {s['gpu']['temp_c']}C  parallel_rec={h['parallel_agents_recommended']}",
            })+"\n")
    if not quiet:
        print(json.dumps({**s, "_headroom": h}, indent=2)[:1200])


def cmd_watch(period: int):
    print(f"[bench] sampling every {period}s, ctrl-c to stop")
    while True:
        cmd_once(quiet=False); time.sleep(period)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--period", type=int, default=60)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.watch: cmd_watch(a.period)
    elif a.once: cmd_once(a.quiet)
    else: cmd_once(False)

if __name__ == "__main__":
    main()
