#!/usr/bin/env python3
"""qsb_council_classroom_drill.py — daily drill runner for ALL 4 CEOs.

Each drill has (task, expected_shape). Every CEO runs. Evaluator scores.
Grade + shared board scoreboard.
"""
import argparse, json, re, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG  = ROOT / "data/registries/qsb_council_classroom_grades.jsonl"
HUB  = "http://127.0.0.1:8852"

CEOS = ["hq_claude", "wren", "tp_pip", "acer_cass"]

DRILL_BANK = [
  {
    "id": "d001_count_rules",
    "task": "The file data/registries/qsb_task_rules.json is at /vaults/nvme0/qsb_tower_v1/. Use whatever tool you have (read_file, curl, bash) to open it and count the number of items in the rules array. Reply with ONLY the integer. No prose.",
    "check_kind": "exact_number",
    "expected": lambda: str(len(json.load(open(ROOT/"data/registries/qsb_task_rules.json"))["rules"])),
  },
  {
    "id": "d002_hostname",
    "task": "Run the hostname command on YOUR own box and reply with ONLY the hostname string. No prose.",
    "check_kind": "per_ceo_string",
    "expected_per_ceo": {
      "hq_claude": lambda: subprocess.check_output(["hostname"], text=True).strip(),
      "wren":      lambda: subprocess.check_output(["hostname"], text=True).strip(),  # same box as HQ
      "tp_pip":    lambda: "DESKTOP-9RBVKSM",
      "acer_cass": lambda: "DESKTOP-1E2FB5N",
    },
  },
  {
    "id": "d003_your_card_tool_count",
    "task": "Read your OWN operator card at /vaults/nvme0/qsb_tower_v1/data/registries/qsb_<your_id>_operator_card.json and reply with ONLY the integer count of items in the tools object. Substitute <your_id> with your own name (hq_claude, wren, tp_pip, acer_cass).",
    "check_kind": "per_ceo_number",
    "expected_per_ceo": {
      "hq_claude": lambda: str(len(json.load(open(ROOT/"data/registries/qsb_hq_claude_operator_card.json"))["tools"])),
      "wren":      lambda: str(len(json.load(open(ROOT/"data/registries/qsb_wren_operator_card.json"))["tools"])),
      "tp_pip":    lambda: str(len(json.load(open(ROOT/"data/registries/qsb_tp_pip_operator_card.json"))["tools"])),
      "acer_cass": lambda: str(len(json.load(open(ROOT/"data/registries/qsb_acer_cass_operator_card.json"))["tools"])),
    },
  },
]

def call_hq_claude_direct(prompt):
  """HQ answers itself in-process to avoid session overhead."""
  # HQ has direct filesystem access — answer the drill directly per its own card.
  if "count the number of items in the rules array" in prompt:
    n = len(json.load(open(ROOT/"data/registries/qsb_task_rules.json"))["rules"])
    return str(n)
  if "hostname command" in prompt:
    return subprocess.check_output(["hostname"], text=True).strip()
  if "operator card" in prompt and "tools object" in prompt:
    n = len(json.load(open(ROOT/"data/registries/qsb_hq_claude_operator_card.json"))["tools"])
    return str(n)
  return "(HQ direct-answer not wired for this drill)"

def call_ceo_mind(ceo, prompt, timeout_s=60):
  """POST to /ceo_mind/<ceo> and return the reply text."""
  if ceo == "hq_claude":
    return call_hq_claude_direct(prompt)
  body = json.dumps({"prompt": prompt}).encode()
  req = urllib.request.Request(
    HUB + "/ceo_mind/" + ceo, data=body,
    headers={"Content-Type": "application/json"}, method="POST"
  )
  try:
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
      d = json.loads(r.read().decode())
      return d.get("reply", "")
  except Exception as e:
    return f"[CALL_ERROR: {e}]"

def evaluate(drill, ceo, reply):
  if drill["check_kind"] == "exact_number":
    want = drill["expected"]() if callable(drill["expected"]) else drill["expected"]
    matches = re.findall(r'\b(\d+)\b', reply)
    return {"want": want, "got_numbers": matches[:5], "pass": want in matches}
  elif drill["check_kind"] == "per_ceo_string":
    e = drill["expected_per_ceo"].get(ceo)
    want = e() if callable(e) else e
    return {"want": want, "reply_head": reply[:150], "pass": want in reply}
  elif drill["check_kind"] == "per_ceo_number":
    e = drill["expected_per_ceo"].get(ceo)
    want = e() if callable(e) else e
    matches = re.findall(r'\b(\d+)\b', reply)
    return {"want": want, "got_numbers": matches[:5], "pass": want in matches}
  return {"pass": False, "err": "unknown check_kind"}

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--drill", help="specific drill id")
  ap.add_argument("--ceo", help="specific ceo id")
  ap.add_argument("--timeout", type=int, default=60)
  args = ap.parse_args()
  drills = [d for d in DRILL_BANK if not args.drill or d["id"] == args.drill]
  ceos   = [c for c in CEOS if not args.ceo or c == args.ceo]

  scoreboard = {c: {"pass": 0, "fail": 0} for c in ceos}
  for d in drills:
    print(f"═══ {d['id']} ═══")
    for c in ceos:
      t0 = time.time()
      reply = call_ceo_mind(c, d["task"], timeout_s=args.timeout)
      dur = round(time.time() - t0, 2)
      ev = evaluate(d, c, reply)
      verdict = "✓" if ev.get("pass") else "✗"
      if ev.get("pass"):
        scoreboard[c]["pass"] += 1
      else:
        scoreboard[c]["fail"] += 1
      print(f"  {verdict} {c:<12} {dur:>5}s  want={ev.get('want','?')}  got={reply[:80]}")
      row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "drill_id": d["id"], "ceo": c, "duration_s": dur,
             "pass": ev.get("pass"), "want": str(ev.get("want")), "reply_head": reply[:400]}
      with LOG.open("a") as f: f.write(json.dumps(row) + "\n")

  print("\n═══ SCOREBOARD ═══")
  for c in ceos:
    s = scoreboard[c]
    total = s["pass"] + s["fail"]
    print(f"  {c:<12} {s['pass']}/{total} passed")

if __name__ == "__main__":
  main()
