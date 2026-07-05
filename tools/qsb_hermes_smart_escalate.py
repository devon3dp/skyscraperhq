#!/usr/bin/env python3
"""qsb_hermes_smart_escalate.py — call hermes3:70b for heavy reasoning.
Per Ross 'wire them all in' 2026-06-26. Mirror of qsb_airllm_ask but for Hermes
family. On-demand: callable when triage_brain flags + when 8b can't.
"""
import argparse, json, subprocess, sys, time
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--max-tokens", type=int, default=400)
    a = p.parse_args()
    t = time.time()
    r = subprocess.run(
        ["python3", "tools/qsb_local_agent_call.py",
          "--model", "hermes3:70b", "--prompt", a.prompt[:6000]],
        cwd="/vaults/nvme0/qsb_tower_v1",
        capture_output=True, text=True, timeout=600,
    )
    d = {"ok": r.returncode == 0, "wall_s": round(time.time()-t,1),
          "stdout": r.stdout[:2000], "stderr": r.stderr[-300:] if r.stderr else ""}
    print(json.dumps(d, indent=2))
if __name__ == "__main__":
    main()
