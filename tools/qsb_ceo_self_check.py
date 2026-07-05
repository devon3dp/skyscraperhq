#!/usr/bin/env python3
"""qsb_ceo_self_check.py — every CEO's self-diagnostic + auto-fix.

Ross 2026-07-05: "everyone must also have self dignostics and fix".

Each CEO runs this against themselves. Checks:
  · dashboard HTTP endpoint responds
  · mind file exists + is valid JSON (for TP/Acer/Wren)
  · ollama endpoint reachable (for local-brain CEOs)
  · self-prompt file being written (for HQ)
  · returns dict {check, status, fix_applied}

Any FAIL runs the matching auto-fix (limited: restart local proc / warm ollama).

Usage
  python3 tools/qsb_ceo_self_check.py hq_claude
  python3 tools/qsb_ceo_self_check.py wren
  python3 tools/qsb_ceo_self_check.py tp_pip     # runs on TP's own laptop
  python3 tools/qsb_ceo_self_check.py all        # runs each check from HQ side
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"

# Ross 2026-07-05: "must report there actions". Each self-fix / self-reboot
# writes a row to town-square + this ledger so Council sees what happened.
sys.path.insert(0, str(ROOT / "tools"))
try:
    from qsb_town_square import post_to_town_square
except Exception:
    def post_to_town_square(*a, **kw): return {}

ACTION_LOG = REG / "qsb_ceo_self_actions.jsonl"

# Per-CEO restart recipe — how to bring THIS ceo's daemon/dash back
# Ross rule "each ceo can restart themselves": these are the self-boot commands
RESTART = {
    "hq_claude": [
        {"cmd": ["python3", str(ROOT/"tools/qsb_hq_claude_dash.py"),
                 "--port", "8850"],
         "kill_pattern": "qsb_hq_claude_dash",
         "why": "HQ dash on :8850 down"},
        {"cmd": ["python3", str(ROOT/"tools/qsb_hq_self_prompt_daemon.py")],
         "kill_pattern": "qsb_hq_self_prompt_daemon",
         "why": "HQ self-prompt daemon stopped writing"},
    ],
    "wren": [
        {"cmd": ["python3", str(ROOT/"tools/qsb_wren_dash.py"), "--port", "8851"],
         "kill_pattern": "qsb_wren_dash",
         "why": "Wren dash on :8851 down"},
        {"cmd": ["python3", str(ROOT/"tools/qsb_wren_evolution_loop.py")],
         "kill_pattern": "qsb_wren_evolution_loop",
         "why": "Wren evo loop dead — self_schedule watcher lost"},
    ],
    "ross": [
        {"cmd": ["python3", str(ROOT/"tools/qsb_boardroom_hub.py"),
                 "--port", "8852"],
         "kill_pattern": "qsb_boardroom_hub",
         "why": "Boardroom (Ross-facing) on :8852 down"},
    ],
    # TP + Acer run on their own laptops — self-reboot happens via SSH from HQ
    # NOT via this daemon. Their local qsb_council_node has to self-heal there.
}


def _stamp_action(ceo: str, action: str, detail: str, verdict: str):
    """Report to Council + ledger."""
    row = {"ts": _utc(), "ceo": ceo, "action": action, "detail": detail, "verdict": verdict}
    try:
        ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ACTION_LOG.open("a") as f:
            f.write(json.dumps(row)+"\n")
    except Exception: pass
    # Stream to Council so Ross sees the action live
    msg = f"🔧 self-heal · {ceo} · {action}: {detail} · verdict={verdict}"
    try:
        post_to_town_square(ceo, msg, to="council", src="self_heal_daemon")
    except Exception: pass

# One profile per CEO — what to check for each
PROFILES = {
    "ross": {
        "endpoint":   "http://127.0.0.1:8852/",
        "role":       "Founding CEO",
        "mind_file":  None,
        "ollama":     None,
    },
    "hq_claude": {
        "endpoint":   "http://127.0.0.1:8850/",
        "role":       "Coordinator",
        "mind_file":  None,
        "ollama":     "http://127.0.0.1:11434/api/tags",
        "prompt_log": REG / "qsb_hq_self_prompts.jsonl",
    },
    "wren": {
        "endpoint":   "http://127.0.0.1:8851/",
        "role":       "Builder-engineer",
        "mind_file":  REG / "qsb_wren_mind.json",
        "ollama":     "http://127.0.0.1:11434/api/tags",
        "gate":       REG / "qsb_wren_local_agentic_gate.json",
    },
    "tp_pip": {
        "endpoint":   "http://192.168.1.74:9110/state",
        "role":       "CEO of ThinkPad",
        "mind_remote":"C:/Users/budds/qsb/mind_tp.json",
        "ollama":     "http://192.168.1.71:11434/api/tags",  # falls back to HQ
    },
    "acer_cass": {
        "endpoint":   "http://192.168.1.78:9000/state",
        "role":       "CEO of Acer laptop",
        "mind_remote":"C:/Users/budds/qsb/mind_acer.json",
        "ollama":     "http://192.168.1.71:11434/api/tags",
    },
}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def http_check(url: str, timeout: int = 5) -> dict:
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return {"ok": 200 <= r.status < 300, "code": r.status, "detail": ""}
    except Exception as e:
        return {"ok": False, "code": 0, "detail": str(e)[:80]}


def check_ceo(name: str) -> dict:
    p = PROFILES.get(name)
    if not p:
        return {"ceo": name, "error": f"unknown ceo · profiles={list(PROFILES)}"}

    out = {"ceo": name, "role": p.get("role","?"), "ts": _utc(), "checks": {}}

    # 1) HTTP endpoint
    ep = http_check(p["endpoint"])
    out["checks"]["endpoint"] = ep

    # 2) mind file (local)
    mf = p.get("mind_file")
    if mf and isinstance(mf, Path):
        if not mf.exists():
            out["checks"]["mind_file"] = {"ok": False, "detail": "missing"}
        else:
            try:
                json.loads(mf.read_text())
                out["checks"]["mind_file"] = {"ok": True,
                                              "size": mf.stat().st_size,
                                              "mtime_age_s": int(datetime.now(timezone.utc).timestamp() - mf.stat().st_mtime)}
            except Exception as e:
                out["checks"]["mind_file"] = {"ok": False, "detail": f"invalid JSON: {e}"}

    # 3) ollama
    if p.get("ollama"):
        oc = http_check(p["ollama"])
        out["checks"]["ollama"] = oc

    # 4) HQ-only: self-prompt daemon is writing
    if name == "hq_claude" and p.get("prompt_log"):
        pl = p["prompt_log"]
        if pl.exists():
            age_s = int(datetime.now(timezone.utc).timestamp() - pl.stat().st_mtime)
            out["checks"]["self_prompt_log"] = {"ok": age_s < 600,
                                                "age_s": age_s,
                                                "detail": "OK" if age_s < 600 else "stale (>10min)"}
        else:
            out["checks"]["self_prompt_log"] = {"ok": False, "detail": "log missing"}

    # 5) Wren gate readable
    if name == "wren" and p.get("gate"):
        g = p["gate"]
        if g.exists():
            try:
                d = json.loads(g.read_text())
                out["checks"]["gate"] = {"ok": bool(d.get("enabled")),
                                         "default_model": d.get("default_model")}
            except Exception as e:
                out["checks"]["gate"] = {"ok": False, "detail": str(e)[:80]}

    # Verdict
    passed = sum(1 for c in out["checks"].values() if c.get("ok"))
    total  = len(out["checks"])
    out["verdict"] = f"{passed}/{total} pass"
    out["healthy"] = (passed == total)
    return out


def auto_fix(name: str, result: dict) -> list:
    """Best-effort fixes. Returns list of fixes applied."""
    fixes = []
    checks = result.get("checks", {})

    # HQ: self_prompt_log stale → restart the daemon
    if name == "hq_claude" and not checks.get("self_prompt_log", {}).get("ok"):
        try:
            subprocess.run(["pkill","-f","qsb_hq_self_prompt_daemon"], check=False, timeout=5)
            subprocess.Popen(
                ["python3", str(ROOT/"tools/qsb_hq_self_prompt_daemon.py")],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            fixes.append("restarted qsb_hq_self_prompt_daemon")
        except Exception as e:
            fixes.append(f"restart failed: {e}")

    # Any: ollama unreachable → try to warm the model
    if not checks.get("ollama", {}).get("ok") and name in ("wren","hq_claude"):
        try:
            body = json.dumps({"model":"qwen2.5:14b","prompt":"hi","stream":False,
                               "options":{"num_predict":2}}).encode()
            req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                          data=body, headers={"Content-Type":"application/json"})
            urllib.request.urlopen(req, timeout=60).read()
            fixes.append("warmed qwen2.5:14b in HQ ollama")
        except Exception as e:
            fixes.append(f"warm failed: {e}")

    return fixes


def self_reboot(ceo: str, result: dict) -> list:
    """When auto-fix wasn't enough — restart the CEO's own daemons/dashes.
    Only for local CEOs (HQ, Wren, Ross-boardroom). Remote CEOs (TP/Acer)
    self-heal on their own boxes."""
    actions = []
    recipes = RESTART.get(ceo, [])
    endpoint_ok = result.get("checks", {}).get("endpoint", {}).get("ok", True)
    if endpoint_ok and not any(not c.get("ok") for c in result.get("checks",{}).values()):
        return actions  # nothing to reboot

    for r in recipes:
        try:
            # kill anything matching the pattern
            subprocess.run(["pkill", "-f", r["kill_pattern"]],
                           check=False, timeout=5)
            time.sleep(0.5)
            # launch fresh
            subprocess.Popen(r["cmd"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
            actions.append(f"restarted {r['kill_pattern']} ({r['why']})")
            _stamp_action(ceo, "self_reboot", r["why"], "reboot fired")
        except Exception as e:
            actions.append(f"reboot-failed {r['kill_pattern']}: {e}")
            _stamp_action(ceo, "self_reboot_failed", str(e)[:80], "error")
    return actions


def heal_loop(ceo: str, interval_s: int = 30):
    """Background loop — probe self, auto-fix if broken, self-reboot if
    still broken, report every action. Runs until killed.

    Reactive network probe every N seconds (not a mind cycle — matches
    the [[feedback_offline_first]] rule of 'graceful degrade'.)"""
    _stamp_action(ceo, "heal_loop_start",
                  f"interval={interval_s}s daemon online", "started")
    consecutive_fails = 0
    while True:
        r = check_ceo(ceo)
        if r.get("healthy"):
            if consecutive_fails > 0:
                _stamp_action(ceo, "recovered",
                              f"back to healthy after {consecutive_fails} fails",
                              "green")
            consecutive_fails = 0
        else:
            consecutive_fails += 1
            _stamp_action(ceo, "fault_detected",
                          f"{r.get('verdict','?')} consecutive={consecutive_fails}",
                          "warn")
            fixes = auto_fix(ceo, r)
            for f in fixes:
                _stamp_action(ceo, "auto_fix", f, "fix_applied")
            # if still broken after N attempts, restart processes
            if consecutive_fails >= 2:
                actions = self_reboot(ceo, r)
                for a in actions:
                    _stamp_action(ceo, "reboot_step", a, "boot_attempt")
                consecutive_fails = 0  # give it a chance to come up
        time.sleep(interval_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ceo", help="ceo name or 'all'")
    ap.add_argument("--fix", action="store_true", help="apply auto-fixes on FAIL")
    ap.add_argument("--heal-loop", action="store_true",
                    help="run as background heal daemon (probe + fix + report)")
    ap.add_argument("--interval", type=int, default=30,
                    help="probe interval seconds (heal-loop only)")
    a = ap.parse_args()

    if a.heal_loop:
        if a.ceo == "all":
            print("--heal-loop is per-ceo, not 'all'. Launch one per CEO.")
            sys.exit(2)
        heal_loop(a.ceo, a.interval)
        return

    targets = list(PROFILES.keys()) if a.ceo == "all" else [a.ceo]
    reports = []
    for t in targets:
        r = check_ceo(t)
        if a.fix and not r.get("healthy") and not r.get("error"):
            r["fixes_applied"] = auto_fix(t, r)
            r["recheck"] = check_ceo(t)
        reports.append(r)
        # print a friendly line per CEO
        v = r.get("verdict","-")
        marker = "✓" if r.get("healthy") else ("✗" if not r.get("error") else "?")
        print(f"  {marker} {t:<10}  {v}  ({r.get('role','?')})")
        for name, c in r.get("checks",{}).items():
            ok = c.get("ok")
            print(f"      · {name:<20}  {'✓' if ok else '✗'}  {c.get('detail') or c.get('code') or c}")
        if r.get("fixes_applied"):
            for f in r["fixes_applied"]:
                print(f"      ⚙ fix: {f}")

    # audit trail
    out_file = REG / "qsb_ceo_self_check.jsonl"
    with out_file.open("a") as f:
        for r in reports:
            f.write(json.dumps(r)+"\n")
    print(f"\n  ledger appended: {out_file}")


if __name__ == "__main__":
    main()
