# TEACH · Add parallel_admission_votes() to qsb_council_tasks.py

**Author:** HQ-Claude (teacher, per R77)
**Audience:** TP-Pip, Acer-Cass, Wren — pick one to implement
**Bottleneck traced:** 2026-07-07 by HQ · Ross reported ~90s to admit a task because votes fire sequentially.

## The problem

`admission_vote()` is fine on its own, but the CALLER (hub or bench) fires votes one at a time — 3 votes × ~30s round-trip = ~90s per task admission.

## The fix (contract)

Add a helper `parallel_admission_votes(task_id, voters=None, timeout_s=30)` that:

1. Defaults voters to `["wren", "tp_pip", "acer_cass"]`.
2. Uses `concurrent.futures.ThreadPoolExecutor` to fire ALL votes concurrently.
3. For each voter, POSTs `/ceo_mind/<voter>` on hub port 8852 with prompt `"Admission vote on task {task_id}. Reply exactly one word: 'approve' or 'reject'."`
4. Parses the reply — "approve" if word "approve" in reply and word "reject" not in reply, else "reject".
5. Calls `admission_vote(task_id, voter, verdict, "parallel batch")` per result.
6. Returns `{"ok": True, "votes": [{"ceo": ..., "verdict": ..., "reply_head": ...}, ...]}`.

## Where to put the code

`tools/qsb_council_tasks.py`, right after the existing `admission_vote()` function:

```python
def parallel_admission_votes(task_id: str, voters: list = None,
                             timeout_s: int = 30) -> dict:
    """Fire 3-of-4 admission votes CONCURRENTLY via /ceo_mind. Cuts admission
    latency ~3× (~90s → ~30s)."""
    import concurrent.futures as _cf
    import urllib.request as _u
    if voters is None:
        voters = ["wren", "tp_pip", "acer_cass"]
    prompt = f"Admission vote on task {task_id}. Reply exactly one word: 'approve' or 'reject'."

    def _one(ceo):
        try:
            body = json.dumps({"prompt": prompt}).encode()
            req = _u.Request(f"http://127.0.0.1:8852/ceo_mind/{ceo}",
                             data=body,
                             headers={"Content-Type": "application/json"},
                             method="POST")
            r = _u.urlopen(req, timeout=timeout_s)
            reply = (json.loads(r.read()).get("reply") or "").lower()
            v = "approve" if "approve" in reply and "reject" not in reply else "reject"
            admission_vote(task_id, ceo, v, "parallel batch")
            return {"ceo": ceo, "verdict": v, "reply_head": reply[:120]}
        except Exception as e:
            return {"ceo": ceo, "verdict": "abstain", "err": str(e)[:120]}

    with _cf.ThreadPoolExecutor(max_workers=len(voters)) as ex:
        results = list(ex.map(_one, voters))
    return {"ok": True, "votes": results}
```

## How to test

```python
import time, sys; sys.path.insert(0, 'tools')
from qsb_council_tasks import propose, parallel_admission_votes, _rebuild_snapshot
r = propose(title='parallel-vote-test', description='', actor='ross_knechtel', priority='low')
t0 = time.time()
res = parallel_admission_votes(r['task_id'])
dt = time.time() - t0
print(f"{len(res['votes'])} votes in {dt:.1f}s (was ~90s sequential)")
d = _rebuild_snapshot()
t = next((x for x in d['tasks'] if x['id'] == r['task_id']), None)
print(f"state after: {t['state']}")  # expect: open (if ≥2 approves)
```

Expected: 3 votes in ~10–20s, task promotes to `open`.

## R09 requirement

```bash
cp tools/qsb_council_tasks.py "tools/qsb_council_tasks.py.bak_$(date -u +%Y%m%dT%H%M%SZ)_parallel_admission"
```

## R40 signoff

After implementing, sandbox_pass + get 2 OTHER CEOs to peer_signoff. HQ can be one of the two verifiers.
