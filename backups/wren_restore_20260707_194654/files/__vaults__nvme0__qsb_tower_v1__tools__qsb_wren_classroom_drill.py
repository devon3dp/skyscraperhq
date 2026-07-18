#!/usr/bin/env python3
"""qsb_wren_classroom_drill.py — daily 3-drill curriculum for Wren.

Each drill has (task, expected_shape). Wren runs. Evaluator scores.
Grade + F47 stamp. Ross reads results.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG  = ROOT / "data/registries/qsb_wren_classroom_grades.jsonl"
AGENT = ROOT / "tools/qsb_wren_local_agent.py"

# Bank of drills (task, expected_regex or exact_number or contains_all)
DRILL_BANK = [
  {
    "id": "d001_count_rules",
    "task": 'Use wren_read_file to read data/registries/qsb_task_rules.json then reply with ONLY the integer number of rules. No prose.',
    "check_kind": "exact_number",
    "expected": lambda: str(len(json.load(open(ROOT/"data/registries/qsb_task_rules.json"))["rules"])),
  },
  {
    "id": "d002_find_r25",
    "task": 'Use wren_grep_repo to find rule R25_NO_STILL in data/registries. Reply with only the file:line that matches.',
    "check_kind": "contains_all",
    "expected": ["qsb_task_rules.json", "R25_NO_STILL"],
  },
  {
    "id": "d003_own_tools_count",
    "task": 'Use wren_read_file on data/registries/qsb_wren_operator_card.json then reply with ONLY the integer count of tools listed. No prose.',
    "check_kind": "exact_number",
    "expected": lambda: str(len(json.load(open(ROOT/"data/registries/qsb_wren_operator_card.json"))["tools"])),
  },
  {
    "id": "d004_hostname",
    "task": 'Use wren_bash with cmd "hostname" and reply with ONLY the hostname string.',
    "check_kind": "exact_string",
    "expected": lambda: subprocess.check_output(["hostname"], text=True).strip(),
  },
  {
    "id": "d005_curl_task_rules",
    "task": 'Use wren_curl to GET http://127.0.0.1:8852/task_rules and reply with ONLY the integer count of rules in the JSON.',
    "check_kind": "exact_number",
    "expected": lambda: str(len(json.load(open(ROOT/"data/registries/qsb_task_rules.json"))["rules"])),
  },
]

def ask_wren(task):
  t0 = time.time()
  try:
    out = subprocess.run(
      ["python3", str(AGENT), "--task", task],
      capture_output=True, text=True, timeout=90)
    dur = time.time() - t0
    # extract final text
    text = out.stdout
    # find text after "wsess"
    m = re.search(r'━{5,}(.+?)━{5,}', text, re.S)
    if not m:
      return {"ok": False, "err": "no wsess block", "raw": text[-500:], "duration_s": round(dur,2)}
    # Get the section between the two ━━━ dividers
    parts = re.split(r'━{5,}', text)
    reply = parts[-2].strip() if len(parts) >= 2 else ""
    return {"ok": True, "reply": reply, "duration_s": round(dur,2)}
  except subprocess.TimeoutExpired:
    return {"ok": False, "err": "timeout 90s"}

def evaluate(drill, reply):
  if drill["check_kind"] == "exact_number":
    want = drill["expected"]() if callable(drill["expected"]) else drill["expected"]
    matches = re.findall(r'\b(\d+)\b', reply)
    return {"want": want, "got_numbers": matches, "pass": want in matches}
  elif drill["check_kind"] == "exact_string":
    want = drill["expected"]() if callable(drill["expected"]) else drill["expected"]
    return {"want": want, "reply_head": reply[:200], "pass": want in reply}
  elif drill["check_kind"] == "contains_all":
    want = drill["expected"]
    hits = [w for w in want if w in reply]
    return {"want": want, "hits": hits, "pass": len(hits) == len(want)}
  return {"pass": False, "err": "unknown check_kind"}

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--drill", help="specific drill id, else random 3")
  ap.add_argument("--all", action="store_true", help="run all drills")
  args = ap.parse_args()
  import random
  if args.drill:
    drills = [d for d in DRILL_BANK if d["id"] == args.drill]
  elif args.all:
    drills = DRILL_BANK
  else:
    drills = random.sample(DRILL_BANK, min(3, len(DRILL_BANK)))
  results = []
  for d in drills:
    print(f"═══ {d['id']} ═══")
    print(f"  task: {d['task'][:100]}")
    r = ask_wren(d["task"])
    if not r.get("ok"):
      print(f"  ✗ agent err: {r.get('err')}")
      results.append({"drill_id": d["id"], "pass": False, "err": r.get("err")})
      continue
    reply = r["reply"]
    ev = evaluate(d, reply)
    verdict = "✓ PASS" if ev.get("pass") else "✗ FAIL"
    print(f"  {verdict}  duration={r['duration_s']}s")
    if not ev.get("pass"):
      print(f"    want: {ev.get('want')}")
      print(f"    got:  {reply[:200]}")
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "drill_id": d["id"], "duration_s": r["duration_s"],
           "pass": ev.get("pass"), "want": str(ev.get("want")), "reply_head": reply[:400]}
    results.append(row)
    with LOG.open("a") as f: f.write(json.dumps(row) + "\n")
  passed = sum(1 for r in results if r.get("pass"))
  print(f"\n═══ SUMMARY: {passed}/{len(results)} passed ═══")
  sys.exit(0 if passed == len(results) else 1)

if __name__ == "__main__":
  main()
