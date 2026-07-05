#!/usr/bin/env python3
"""qsb_thermal_guard.py — poll CPU/GPU temps, auto-throttle on overheat.

Read-only by default. Throttling needs sudo (via SUDO_PASSWORD env var).

States, in escalating order:
  NORMAL    — full performance restored
  WARN      — log only, alert in journal
  THROTTLE  — clamp GPU power limit + clock + CPU max freq
  CRITICAL  — unload Ollama models + pause non-essential heavy procs

Recovers (loosens by one step) after N consecutive cool ticks.

Logs to data/registries/qsb_thermal_tail.jsonl every tick.
State to    data/registries/qsb_thermal_state.json.
PID at      data/run/qsb_thermal_guard.pid.

Thresholds in config/qsb_thermal_thresholds.json (auto-written w/ defaults).
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TAIL = ROOT / "data/registries/qsb_thermal_tail.jsonl"
STATE = ROOT / "data/registries/qsb_thermal_state.json"
PIDFILE = ROOT / "data/run/qsb_thermal_guard.pid"
CFG = ROOT / "config/qsb_thermal_thresholds.json"
LOG = ROOT / "logs/intelligence/qsb_thermal_guard.log"

DEFAULTS = {
    "poll_seconds": 15,
    "cool_ticks_to_recover": 8,
    "gpu_warn_c": 72,
    "gpu_throttle_c": 78,
    "gpu_critical_c": 84,
    "cpu_warn_c": 80,
    "cpu_throttle_c": 88,
    "cpu_critical_c": 94,
    "gpu_pl_throttle_w": 250,
    "gpu_clock_throttle_mhz": [210, 1500],
    "cpu_max_freq_throttle_khz": 3800000,
    "cpu_max_freq_critical_khz": 2800000,
    "ollama_unload_on_critical": True,
}

for p in (TAIL.parent, STATE.parent, PIDFILE.parent, CFG.parent, LOG.parent):
    p.mkdir(parents=True, exist_ok=True)
if not CFG.exists():
    CFG.write_text(json.dumps(DEFAULTS, indent=2))


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_cfg() -> dict:
    try:
        d = json.loads(CFG.read_text())
        return {**DEFAULTS, **d}
    except Exception:
        return DEFAULTS.copy()


def gpu_snapshot() -> dict:
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,power.draw,power.limit,utilization.gpu,fan.speed,clocks.gr,clocks.mem",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
        )
        vals = [v.strip() for v in r.stdout.strip().split(",")]
        return {
            "temp_c": int(vals[0]) if vals[0].isdigit() else None,
            "power_w": float(vals[1]),
            "power_limit_w": float(vals[2]),
            "util_pct": int(vals[3]),
            "fan_pct": int(vals[4]),
            "clock_gr_mhz": int(vals[5]),
            "clock_mem_mhz": int(vals[6]),
        }
    except Exception as e:
        return {"error": str(e)[:80]}


def cpu_temp_c() -> float | None:
    """Return the hottest 'package'/'tctl'/'tdie' temp from `sensors`."""
    try:
        r = subprocess.run(["sensors", "-A"], capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    hottest = None
    for ln in r.stdout.splitlines():
        low = ln.lower()
        if any(k in low for k in ("tctl", "tdie", "package", "tccd", "core 0", "cpu temp")):
            for tok in ln.split():
                if tok.startswith("+") and tok.endswith("C"):
                    try:
                        v = float(tok[1:-2])
                        if hottest is None or v > hottest:
                            hottest = v
                    except ValueError:
                        pass
    return hottest


def sudo(cmd: list[str]) -> tuple[int, str]:
    pw = os.environ.get("SUDO_PASSWORD")
    if not pw:
        envf = ROOT / "floors/floor_28_security_department/vault/.env.sudo"
        if envf.exists():
            for ln in envf.read_text().splitlines():
                ln = ln.strip()
                if ln.startswith("SUDO_PASSWORD="):
                    pw = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not pw:
        return 99, "no SUDO_PASSWORD"
    try:
        r = subprocess.run(
            ["sudo", "-S", "-p", "", "-n"] + cmd,
            input=None, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return 0, (r.stdout or "").strip()
        r = subprocess.run(
            ["sudo", "-S", "-p", ""] + cmd,
            input=pw + "\n", capture_output=True, text=True, timeout=15,
        )
        return r.returncode, ((r.stderr or "") + (r.stdout or "")).strip()[:240]
    except Exception as e:
        return 98, str(e)[:200]


def apply_gpu_pl(w: int) -> str:
    rc, out = sudo(["nvidia-smi", "-pl", str(w)])
    return f"gpu_pl={w} rc={rc} {out[:80]}"


def apply_gpu_lgc(lo: int, hi: int) -> str:
    rc, out = sudo(["nvidia-smi", "-lgc", f"{lo},{hi}"])
    return f"gpu_lgc={lo},{hi} rc={rc} {out[:80]}"


def reset_gpu_lgc() -> str:
    rc, out = sudo(["nvidia-smi", "-rgc"])
    return f"gpu_rgc rc={rc} {out[:80]}"


def apply_cpu_max_khz(khz: int) -> str:
    n = os.cpu_count() or 1
    msgs = []
    for i in range(n):
        path = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_max_freq"
        rc, out = sudo(["sh", "-c", f"echo {khz} > {path}"])
        if rc != 0:
            msgs.append(f"cpu{i}_rc{rc}")
    return f"cpu_max_khz={khz} fails={len(msgs)}"


def cpu_max_khz_default() -> int:
    try:
        return int(Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").read_text().strip())
    except Exception:
        return 0


def unload_ollama_models() -> str:
    try:
        r = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        names = []
        for ln in r.stdout.splitlines()[1:]:
            parts = ln.split()
            if parts:
                names.append(parts[0])
        for n in names:
            subprocess.run(["ollama", "stop", n], capture_output=True, text=True, timeout=10)
        return f"ollama_unloaded={names}"
    except Exception as e:
        return f"ollama_unload_err={str(e)[:80]}"


def level_for(gt: float | None, ct: float | None, cfg: dict) -> str:
    g = gt or 0
    c = ct or 0
    if g >= cfg["gpu_critical_c"] or c >= cfg["cpu_critical_c"]:
        return "CRITICAL"
    if g >= cfg["gpu_throttle_c"] or c >= cfg["cpu_throttle_c"]:
        return "THROTTLE"
    if g >= cfg["gpu_warn_c"] or c >= cfg["cpu_warn_c"]:
        return "WARN"
    return "NORMAL"


LEVEL_RANK = {"NORMAL": 0, "WARN": 1, "THROTTLE": 2, "CRITICAL": 3}


def write_state(d: dict):
    STATE.write_text(json.dumps(d, indent=2))


def write_tail(d: dict):
    with TAIL.open("a") as f:
        f.write(json.dumps(d) + "\n")


def stamp_f47(kind: str, subject: str, extra: dict | None = None):
    rec = {
        "ts": utc_iso(),
        "kind": kind,
        "role": "thermal_guard",
        "subject": subject,
    }
    if extra:
        rec.update(extra)
    with (ROOT / "data/registries/qsb_f47_team_records.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single read + state print, no daemon")
    ap.add_argument("--no-throttle", action="store_true", help="monitor only, never call sudo")
    ap.add_argument("--reset", action="store_true", help="reset GPU clock + CPU max to defaults and exit")
    args = ap.parse_args()

    cpu_max_default = cpu_max_khz_default()

    if args.reset:
        msgs = [reset_gpu_lgc(), apply_gpu_pl(300), apply_cpu_max_khz(cpu_max_default) if cpu_max_default else "cpu_default_unknown"]
        print(" ; ".join(str(m) for m in msgs))
        return 0

    PIDFILE.write_text(str(os.getpid()))

    state = {"level": "NORMAL", "cool_ticks": 0, "applied": {}, "started_at": utc_iso()}

    def handle_term(signum, frame):
        write_tail({"ts": utc_iso(), "event": "shutdown", "signal": signum})
        sys.exit(0)
    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)

    stamp_f47("thermal_guard_start", "qsb_thermal_guard.py started", {"pid": os.getpid()})

    while True:
        cfg = load_cfg()
        gpu = gpu_snapshot()
        ct = cpu_temp_c()
        gt = gpu.get("temp_c")
        new_level = level_for(gt, ct, cfg)

        if args.once:
            print(json.dumps({"ts": utc_iso(), "level": new_level, "gpu_c": gt, "cpu_c": ct, "gpu": gpu}, indent=2))
            return 0

        tail = {
            "ts": utc_iso(),
            "level": new_level,
            "gpu_c": gt, "cpu_c": ct,
            "gpu_power_w": gpu.get("power_w"),
            "gpu_util": gpu.get("util_pct"),
            "gpu_clock_mhz": gpu.get("clock_gr_mhz"),
            "fan_pct": gpu.get("fan_pct"),
        }
        write_tail(tail)

        prev_level = state["level"]
        if LEVEL_RANK[new_level] > LEVEL_RANK[prev_level]:
            state["cool_ticks"] = 0
            if not args.no_throttle:
                applied = state.setdefault("applied", {})
                if new_level == "THROTTLE":
                    applied["gpu_pl"] = apply_gpu_pl(cfg["gpu_pl_throttle_w"])
                    lo, hi = cfg["gpu_clock_throttle_mhz"]
                    applied["gpu_lgc"] = apply_gpu_lgc(int(lo), int(hi))
                    applied["cpu_max"] = apply_cpu_max_khz(int(cfg["cpu_max_freq_throttle_khz"]))
                elif new_level == "CRITICAL":
                    applied["gpu_pl"] = apply_gpu_pl(cfg["gpu_pl_throttle_w"])
                    lo, hi = cfg["gpu_clock_throttle_mhz"]
                    applied["gpu_lgc"] = apply_gpu_lgc(int(lo), int(hi))
                    applied["cpu_max"] = apply_cpu_max_khz(int(cfg["cpu_max_freq_critical_khz"]))
                    if cfg.get("ollama_unload_on_critical"):
                        applied["ollama"] = unload_ollama_models()
                stamp_f47("thermal_escalate", f"{prev_level} -> {new_level}",
                          {"gpu_c": gt, "cpu_c": ct, "applied": applied})
            state["level"] = new_level

        elif LEVEL_RANK[new_level] < LEVEL_RANK[prev_level]:
            state["cool_ticks"] = state.get("cool_ticks", 0) + 1
            if state["cool_ticks"] >= cfg["cool_ticks_to_recover"]:
                state["cool_ticks"] = 0
                if not args.no_throttle and state["applied"]:
                    restored = {}
                    restored["gpu_rgc"] = reset_gpu_lgc()
                    restored["gpu_pl"] = apply_gpu_pl(300)
                    if cpu_max_default:
                        restored["cpu_max"] = apply_cpu_max_khz(cpu_max_default)
                    state["applied"] = {}
                    stamp_f47("thermal_recover", f"{prev_level} -> {new_level}",
                              {"gpu_c": gt, "cpu_c": ct, "restored": restored})
                state["level"] = new_level
        else:
            state["cool_ticks"] = 0

        state["last_tick"] = tail
        write_state(state)
        time.sleep(int(cfg["poll_seconds"]))


if __name__ == "__main__":
    sys.exit(main() or 0)
