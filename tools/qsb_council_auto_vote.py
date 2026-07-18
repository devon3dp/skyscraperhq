#!/usr/bin/env python3
"""qsb_council_auto_vote.py — GAPs 1+2 partial fix (HQ-side).

Wraps /ceo_mind/<ceo> calls: when a peer replies to an admission-vote prompt,
parse "approve|reject" from the reply + auto-record the vote on the shared
board so peers don't need to POST to /tasks/admission_vote themselves.

Also parses "claim" and "signoff" verbs. Extraction is regex — not perfect but
closes the loop until peer-side tool_call round-trip is fixed.
"""
import argparse, json, re, sys, urllib.request
sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
import qsb_council_tasks as tasks

HUB = "http://127.0.0.1:8852"

VOTE_RX = re.compile(r"\b(APPROVE|approve|APPROVED|approved|REJECT|reject|REJECTED|rejected)\b")
CLAIM_RX = re.compile(r"\b(I claim|claim it|claiming|I take|taking this)\b", re.I)
SIGNOFF_RX = re.compile(r"\bpeer[\s\-_]signoff\b|\bsignoff\b|\bapprove\b", re.I)


def call_peer(ceo, prompt, timeout_s=45):
    body = json.dumps({"prompt": prompt}).encode()
    req = urllib.request.Request(HUB + "/ceo_mind/" + ceo,
                                 data=body, headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        return json.loads(r.read().decode()).get("reply", "")


def extract_vote(reply):
    m = VOTE_RX.search(reply)
    if not m: return None
    w = m.group(1).lower()
    if "reject" in w: return "reject"
    if "approve" in w: return "approve"
    return None


def extract_first_line_reason(reply, max_chars=200):
    for line in reply.strip().splitlines():
        line = line.strip("*# -")
        if len(line) > 10 and "APPROVE" not in line.upper()[:20]:
            return line[:max_chars]
    return reply[:max_chars]


def admission_vote_all(task_id, ceos=("wren","tp_pip","acer_cass")):
    """Ask each peer to admission-vote + auto-record on board."""
    prompt = (f"Admission vote for task {task_id}. Reply APPROVE or REJECT + one-line reason. "
              f"R05/R22. HQ will auto-record your vote on the board.")
    results = {}
    for ceo in ceos:
        try:
            reply = call_peer(ceo, prompt)
            vote = extract_vote(reply)
            reason = extract_first_line_reason(reply)
            if vote:
                tasks.admission_vote(task_id, ceo, vote, reason)
                results[ceo] = {"vote": vote, "reason": reason[:100], "recorded": True}
            else:
                results[ceo] = {"vote": None, "reply_head": reply[:200], "recorded": False,
                                "note": "no APPROVE/REJECT verb in reply"}
        except Exception as e:
            results[ceo] = {"error": str(e)[:150]}
    return results


def claim_prompt(task_id, ceos):
    """Ask each peer if they claim the task; auto-record first CLAIM."""
    prompt = (f"Task {task_id} is open. Do you CLAIM it? Reply CLAIM or PASS + one-line reason. "
              f"First CLAIM wins.")
    for ceo in ceos:
        try:
            reply = call_peer(ceo, prompt)
            if CLAIM_RX.search(reply):
                tasks.claim(task_id, ceo)
                return {"claimed_by": ceo, "reason": extract_first_line_reason(reply)}
        except Exception as e:
            pass
    return {"claimed_by": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--action", choices=["admission","claim","signoff"], default="admission")
    ap.add_argument("--ceos", default="wren,tp_pip,acer_cass")
    args = ap.parse_args()
    ceos = [c.strip() for c in args.ceos.split(",") if c.strip()]
    if args.action == "admission":
        r = admission_vote_all(args.task_id, ceos)
    elif args.action == "claim":
        r = claim_prompt(args.task_id, ceos)
    else:
        r = {"todo": "signoff extractor"}
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
