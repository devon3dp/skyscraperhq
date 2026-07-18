#!/usr/bin/env python3
"""wren_fan_control.py — Wren's own fan tool. Read + set GPU fans."""
import argparse, subprocess, json, sys

def read_state():
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,fan.speed,temperature.gpu,utilization.gpu,memory.used",
         "--format=csv,noheader"], text=True, timeout=5).strip()
    name, fan, temp, util, mem = [x.strip() for x in out.split(",")]
    return {"gpu": name, "fan_pct": fan, "temp_c": temp, "util_pct": util, "vram": mem}

def set_fan(target_pct):
    if not (0 <= target_pct <= 100):
        return {"ok": False, "error": f"target {target_pct} out of range 0-100"}
    cmd = ("DISPLAY=:1 nvidia-settings -c :1 "
           f'-a "[gpu:0]/GPUFanControlState=1" -a "[fan:0]/GPUTargetFanSpeed={target_pct}"')
    r = subprocess.run(["sudo", "-S", "sh", "-c", cmd], input="ross\n", text=True,
                       capture_output=True, timeout=10)
    return {"ok": r.returncode == 0, "target": target_pct, "stdout": r.stdout.strip()[-200:]}

def main():
    ap = argparse.ArgumentParser(description="Wren fan control")
    ap.add_argument("--get", action="store_true", help="print current fan/temp/util as JSON")
    ap.add_argument("--set", type=int, metavar="N", help="set fan to N percent (0-100)")
    args = ap.parse_args()
    if args.set is not None:
        print(json.dumps(set_fan(args.set)))
    else:
        print(json.dumps(read_state()))

if __name__ == "__main__":
    main()
