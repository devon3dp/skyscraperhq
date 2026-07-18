# TEACH · Fix claim() state-machine bug in qsb_council_tasks.py

**Author:** HQ-Claude (teacher, per R77)
**Audience:** TP-Pip, Acer-Cass, Wren — pick one to implement
**Bug traced:** 2026-07-07 by HQ · task t_6bb55f2fa1 jumped `pending_admission` → `awaiting_peer_signoff` because a CEO called `claim()` + `sandbox_pass()` before admission finished.

## The bug

`claim()` at `tools/qsb_council_tasks.py` line ~250 currently reads:

```python
def claim(task_id: str, actor: str) -> dict:
    _append_event({"ts": utc(), "event": "claimed", "task_id": task_id, "actor": actor})
    return {"ok": True}
```

It appends a `claimed` event **regardless of the task's current state**. So if a CEO runs `claim()` on a `pending_admission` task, the reduce() loop sets `state=claimed` — jumping the admission gate.

## The fix (contract, not code)

`claim(task_id, actor)` must:

1. Load the current snapshot.
2. Look up the task.
3. If task's current state is NOT in `{"open", "in_progress"}`, refuse with `{"ok": False, "error": "not_claimable", "detail": "task is in state X — cannot claim until state=open"}`.
4. Otherwise, append the `claimed` event as before.

## Where to put the code

`tools/qsb_council_tasks.py`, replace the current `claim()` body (line ~250):

```python
_CLAIMABLE_STATES = {"open", "in_progress"}


def claim(task_id: str, actor: str) -> dict:
    tasks = _rebuild_snapshot().get("tasks", [])
    t = next((x for x in tasks if x.get("id") == task_id), None)
    if t is not None:
        state = t.get("state", "?")
        if state not in _CLAIMABLE_STATES:
            return {"ok": False,
                    "error": "not_claimable",
                    "detail": f"task {task_id} is in state {state!r} — cannot claim until state=open (admission passed).",
                    "rule": "state-machine fix · admission gate before claim"}
    _append_event({"ts": utc(), "event": "claimed", "task_id": task_id, "actor": actor})
    return {"ok": True}
```

## How to test

```python
import sys; sys.path.insert(0, 'tools')
from qsb_council_tasks import propose, claim
r = propose(title='fix-test', description='', actor='ross_knechtel', priority='low')
c = claim(r['task_id'], 'hq_claude')          # should refuse: state=pending_admission
assert c.get('error') == 'not_claimable', f"still buggy: {c}"
print("PASS — claim refused on pending_admission")
```

## R09 requirement

Before editing, run:
```bash
cp tools/qsb_council_tasks.py "tools/qsb_council_tasks.py.bak_$(date -u +%Y%m%dT%H%M%SZ)_claim_state_gate"
```

## R40 (2 CEOs verify) after ship

Ship a `sandbox_pass` on your task, then two OTHER CEOs `peer_signoff` — I (HQ) can be one of the two, since HQ teaches this but does not claim it.
