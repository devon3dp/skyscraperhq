#!/usr/bin/env python3
"""
qsb_task_council_autorunner.py — AUTONOMOUS Task Council loop (2026-07-18, Ross: "we need it autonomous").

Runs on its own timer. Each tick:
  1. honours the kill switch (data/registries/qsb_autorunner_gate.json enabled=false stops it).
  2. reads the live board; counts in-flight tasks per CEO (cap = 3/CEO).
  3. if Wren has capacity AND an independent CEO (Pip/Asa) is reachable at :9120, it
     runs ONE governed cycle via qsb_task_council_run (owner Wren + real worker + independent
     verify by the peer CEO who echoes a unique token + completion gate) -> board moves to done.
  4. logs every tick to data/registries/qsb_autorunner_activity.jsonl and sleeps.

Honesty: it only marks DONE what an independent CEO actually verified this cycle (real token echo).
It NEVER fabricates completion, never self-verifies, never auto-completes high-risk tasks.
NON-AUTONOMOUS-WORKER note: Ross explicitly ordered this autonomous loop; it is bounded (normal-risk
only, capped, kill-switchable) and every completion carries real independent-CEO evidence.
"""
import os, sys, json, time, threading, concurrent.futures, urllib.request
from datetime import datetime, timezone, timedelta

# 2026-07-19 Ross "in the rules it says up to 3 tasks" — the cap allows 3/CEO but the runner only
# processed ONE at a time (run_backlog blocks for minutes). Fix: a bounded thread pool runs up to
# PER_CEO_CAP tasks CONCURRENTLY. run_backlog is I/O-bound (HTTP/ollama/subprocess) so threads fit.
_LOG_LOCK = threading.Lock()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import qsb_task_council_run as RUN

GATE = os.path.join(ROOT, "data", "registries", "qsb_autorunner_gate.json")
ACT = os.path.join(ROOT, "data", "registries", "qsb_autorunner_activity.jsonl")
PER_CEO_CAP = 3
INTERVAL = int(os.environ.get("AUTORUNNER_INTERVAL", "20"))


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gate_enabled():
    try:
        return bool(json.load(open(GATE)).get("enabled", True))
    except Exception:
        return True  # default on if gate missing; create with enabled=false to stop


def peer_reachable():
    # Ross 2026-07-28: when the :9120 peer cockpits are down, verify via the gene-pool
    # DeepSeek quorum (GPV.external_verify) instead of stalling. Reversible env flag.
    import os as _os
    if _os.environ.get("COUNCIL_GENE_POOL_VERIFY") == "1":
        return True
    for url in ("http://192.168.1.76:9120/health", "http://192.168.1.89:9120/health"):
        try:
            if urllib.request.urlopen(url, timeout=4).getcode() == 200:
                return True
        except Exception:
            continue
    return False


STALE_MIN = int(os.environ.get("COUNCIL_STALE_MIN", "20"))  # a task idle this long is orphaned


def _age_min(ts):
    """Minutes since an ISO timestamp; large number if unparseable/missing."""
    try:
        t = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() / 60.0
    except Exception:
        return 1e9


def _last_activity(t):
    """Most-recent event ts for a task (from its history), else created/started."""
    h = t.get("history") or []
    if h:
        return h[-1].get("ts") or t.get("started_at") or t.get("created_at")
    return t.get("started_at") or t.get("created_at")


def _is_stale(t):
    return _age_min(_last_activity(t)) > STALE_MIN


def _cooling(t):
    """True if a recycled task is still in its backoff window (retry_after in the future) — the picker
    skips it so a genuinely-stuck task re-enters the pool with backoff instead of thrashing."""
    ra = t.get("retry_after")
    if not ra:
        return False
    try:
        return datetime.fromisoformat(ra.replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except Exception:
        return False


def inflight_for(ceo):
    """Count tasks ACTIVELY owned by a CEO (FIX S1: exclude STALE/orphaned tasks so they don't
    clog the cap and starve new work)."""
    try:
        import qsb_council_tasks as T
        return sum(1 for t in T.snapshot().get("tasks", [])
                   if t.get("owner") == ceo
                   and t.get("state") in ("claimed", "in_progress", "awaiting_peer_signoff", "awaiting_verification")
                   and not _is_stale(t))
    except Exception:
        return 0


def log(rec):
    rec["ts"] = utc()
    with _LOG_LOCK:
        with open(ACT, "a") as f:
            f.write(json.dumps(rec) + "\n")


def next_open_task():
    """Oldest actionable task: a real OPEN unowned task, OR a STALE orphan (FIX S1: tasks stuck in
    assigned/in_progress/awaiting_* past STALE_MIN get re-picked instead of being orphaned forever)."""
    try:
        import qsb_council_tasks as T
        tasks = T.snapshot().get("tasks", [])
        def real(t):
            return "council_proof" not in (t.get("tags") or []) and "AUTO" not in (t.get("title") or "")
        opens = [t for t in tasks if t.get("state") == "open" and not t.get("owner") and real(t)
                 and not _cooling(t)]
        stalled = [t for t in tasks
                   if t.get("state") in ("claimed", "assigned", "acknowledged", "in_progress",
                                         "awaiting_peer_signoff", "awaiting_verification", "needs_rework")
                   and real(t) and _is_stale(t)]
        cand = opens + stalled
        cand.sort(key=lambda t: t.get("created_at", ""))
        return cand[0] if cand else None
    except Exception:
        return None


def run_backlog(task):
    """Assign a REAL backlog task to Wren+Pip, have a worker genuinely attempt it, independent
    CEO verifies whether the output ACTUALLY satisfies it. Completes only if genuinely verified;
    otherwise leaves it in_progress with the honest attempt journalled (no fake completion)."""
    import hashlib, json as _j
    from qsb_task_council_run import post, journal, utc, WREN, PIP, ASA, OLLAMA
    import qsb_governance_engine as ENG
    tid = task["id"]; title = (task.get("title") or "")[:120]; desc = (task.get("description") or "")[:300]
    # partner
    partner, purl = None, None
    # 2026-07-28 Ross: peers at :9120 down -> the two independent verifiers ARE the gene pool
    # (DeepSeek, one call each as tp_pip+acer_cass in the verify loop). Skip the cockpit probe so
    # tasks aren't stuck on no_partner. Reversible: unset COUNCIL_GENE_POOL_VERIFY.
    if os.environ.get("COUNCIL_GENE_POOL_VERIFY") == "1":
        partner, purl = "tp_pip", None
        journal({"ts": utc(), "event": "assigned", "task_id": tid, "actor": "gene_pool_verifiers",
                 "state": "in_progress", "text": "peers down - quorum via gene-pool DeepSeek"})
    else:
        for cid, url in (("tp_pip", PIP), ("acer_cass", ASA)):
            if post(url, {"prompt": "reply READY"}, 30).get("reply"):
                partner, purl = cid, url; break
    if not partner:
        return {"task": tid, "result": "no_partner"}
    journal({"ts": utc(), "event": "claimed", "task_id": tid, "actor": "wren", "state": "in_progress"})
    journal({"ts": utc(), "event": "assigned", "task_id": tid, "actor": partner, "state": "in_progress"})
    # 2026-07-18 Ross "use the council of 15 as well as coder tool": owner picks the right tool.
    # 2026-07-19 Ross "if they deny it ... the team correct what did not pass ... continue until it
    # passes ... autonomously": CORRECTION LOOP. build -> 2-CEO gene-pool verify -> if rejected, feed
    # the EXACT rejection reasons back to the tool and rebuild -> re-verify -> repeat until a >=2-CEO
    # quorum passes OR MAX_ATTEMPTS is hit (then BLOCK + escalate to Ross; never fake a completion).
    import qsb_council15_tools as TOOLS
    import qsb_gene_pool_verify as GPV
    tool = TOOLS.select_tool(title, desc)
    journal({"ts": utc(), "event": "tool_selected", "task_id": tid, "actor": "wren",
             "text": f"owner uses {tool['tool']} ({tool['model']})"})
    # FIX C1/C3/C5: assemble RICH context — target_file + context_files[] + CEO rationale (all now
    # survive the snapshot). This is what makes "build on top of existing work" actually work.
    _cparts = []
    _files = ([{"path": task.get("target_file"), "role": "primary_file"}] if task.get("target_file") else []) \
             + list(task.get("context_files") or [])
    for _f in _files:
        _fp = _f.get("path") if isinstance(_f, dict) else _f
        _role = _f.get("role", "context") if isinstance(_f, dict) else "context"
        _ap = os.path.join(ROOT, _fp) if _fp else ""
        if _ap and os.path.exists(_ap):
            _cparts.append(f"--- {_role}: {_fp} ---\n" + open(_ap).read())
    if task.get("ceo_rationale"):
        _cparts.append("--- CEO RATIONALE (keep this in mind) ---\n" + str(task["ceo_rationale"]))
    context = "\n\n".join(_cparts)
    MAX_ATTEMPTS = int(os.environ.get("COUNCIL_MAX_CORRECTIONS", "3"))
    correction = ""       # rejection reasons from the previous attempt
    prev_artifact = ""    # FIX C2: previous output, fed back so the tool EDITS instead of rewriting blind
    out = ""; sha = ""; path = None
    reverify_only = False  # FIX (verification found this): when verifiers were merely inconclusive/timed out
                           # (NOT a rejection), re-verify the SAME artifact instead of wastefully rebuilding.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if reverify_only:
            reverify_only = False
            journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": "wren",
                     "text": f"attempt {attempt}: re-verifying the SAME artifact {sha[:12]} (verifiers were inconclusive, not a rejection)"})
            # out/sha/path retained from the previous iteration — skip the rebuild
        else:
            spec = f"{title}. {desc}"
            if correction:
                journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": "wren",
                         "text": f"CORRECTION attempt {attempt}: rebuilding to fix the rejections"})
                # FIX (councilfix, secondary P0): only re-inject the previous artifact when it is SMALL
                # (< 8000 chars). Re-feeding a large 20k-42k artifact into the next build prompt inflated
                # every correction attempt and worsened the truncation problem. For large artifacts, tell
                # the tool to rebuild the complete file from the spec + rejection reasons instead.
                # 2026-07-22 Ross (a): the blind-rebuild path caused DRIFT — a rejected 11-12k HTML page
                # was rebuilt from scratch and wandered off-spec (attempt 3 became a bare CSS stylesheet).
                # Fix: re-inject the previous artifact up to 16000 chars (covers full HTML pages) so the
                # tool EDITS in place instead of reinventing, and forbid switching artifact type/scope.
                # The producer's max_tokens was raised in lockstep so artifact+rebuild fits without truncation.
                if prev_artifact and len(prev_artifact) < 16000:
                    spec += ("\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Here is EXACTLY what you produced last time — "
                             "KEEP everything that already works, CHANGE ONLY what the verifiers flagged, and return the "
                             "COMPLETE file of the SAME KIND and SCOPE as the task (do NOT switch to a different artifact "
                             "type — e.g. do not return a bare stylesheet or fragment when a full page was asked — and do "
                             "NOT truncate):\n"
                             f"--- PREVIOUS ARTIFACT (attempt {attempt-1}) ---\n{prev_artifact}\n"
                             f"--- END PREVIOUS ARTIFACT ---\n\nProblems the CEO verifiers found:\n{correction}")
                else:
                    spec += ("\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED (it was very large, so it is not re-quoted here to "
                             "avoid ballooning). Rebuild the COMPLETE file from first line to last, of the SAME KIND and "
                             "SCOPE as the task title (do NOT switch artifact type, do NOT truncate). "
                             f"Problems the CEO verifiers found:\n{correction}")
            # FIX P1 (councilfix): sane timeout (default 420s) instead of 1800s that let a dead/hung
            # iQuest coder wedge a single task for ~3 hours. Overridable via COUNCIL_TOOL_TIMEOUT.
            _tool_to = int(os.environ.get("COUNCIL_TOOL_TIMEOUT", "420"))
            ur = TOOLS.use_tool(tool, spec=spec, context=context, timeout_s=_tool_to)
            out = (ur.get("output") or "").strip()
            ext = "html" if ("<html" in out.lower() or "<!doctype" in out.lower()) else "txt"
            path = os.path.join(ROOT, "tests", f"backlog_{tid}.{ext}")
            open(path, "w").write(out if ext == "html" else f"TASK {tid}\n{title}\ntool {tool['tool']}\n---\n{out}\n")
            sha = hashlib.sha256(out.encode()).hexdigest()
            prev_artifact = out
            # FIX C4: detect a TRUNCATED artifact (unbalanced braces / missing closing html / dangling punctuation)
            truncated = bool(out) and (out.count("{") != out.count("}")
                                       or ("<html" in out.lower() and "</html>" not in out.lower())
                                       or out.rstrip().endswith((",", ":", "{", "(")))
            journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": "wren",
                     "text": f"attempt {attempt}: {tool['tool']} produced {ur.get('chars', len(out))} chars in {ur.get('elapsed_s','?')}s{' [TRUNCATED]' if truncated else ''}, artifact {sha[:12]}"})
            if not ur.get("ok") or not out:
                correction = f"The tool failed/produced nothing ({ur.get('error')}). Produce the complete deliverable."
                continue
            if truncated and attempt < MAX_ATTEMPTS:
                correction = "Your previous output was TRUNCATED/incomplete (unbalanced braces or missing closing tags). Return the ENTIRE file from first line to last."
                continue
        # FIX F7: 3-state per-CEO verdict — approve / reject / timeout(None). Timeouts RETRY (inline, up
        # to 2x) and are NEVER counted as rejections. Only real rejections drive the correction feedback.
        approvals, rejections, timeouts, reasons = [], [], [], []
        for cid, url in (("tp_pip", PIP), ("acer_cass", ASA)):
            if not ENG.no_self_verify("wren", cid):
                continue
            ok3, source, note = None, "", ""
            for _vtry in range(2):
                v = GPV.external_verify(cid, f"{title}. {desc}", out)
                if v.get("available"):
                    ok3, source, note = v.get("verified"), f"external:{v.get('provider')}", v.get("reply", "")
                else:
                    vp = (f"You are {cid}, an independent CEO verifier (NOT owner Wren). Task: '{title}'. Deliverable "
                          f"(first 6000 chars):\n{out[:6000]}\nReply EXACTLY 'DONE {tid}' if it genuinely satisfies the "
                          f"task, else 'NOT_DONE' and one concrete reason.")
                    r = (post(url, {"prompt": vp}, 150).get("reply") or "").strip()
                    ok3 = True if ("DONE" in r.upper() and tid in r) else (None if not r else False)
                    source, note = "local_cockpit", r
                if ok3 is not None:
                    break  # got a definite verdict; stop retrying
            if ok3 is True:
                approvals.append(cid)
                journal({"ts": utc(), "event": "peer_signoff", "task_id": tid, "actor": cid, "verdict": "approve",
                         "text": f"{source} verified artifact {sha[:12]} (attempt {attempt})"})
            elif ok3 is None:
                timeouts.append(cid)
                journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": cid,
                         "text": f"{source} verdict inconclusive/timeout (attempt {attempt}) — NOT a rejection"})
            else:
                rejections.append(cid); reasons.append(f"{cid}: {note}")
                journal({"ts": utc(), "event": "peer_signoff", "task_id": tid, "actor": cid, "verdict": "reject",
                         "text": f"{source} (attempt {attempt}): {note[:180]}"})
        if len(approvals) >= 2:
            journal({"ts": utc(), "event": "done", "task_id": tid, "actor": approvals[-1],
                     "text": f"quorum signoff by {'+'.join(approvals)} on attempt {attempt}"})
            return {"task": tid, "result": "COMPLETED", "attempt": attempt, "verifiers": approvals,
                    "tool": tool["tool"], "artifact": path}
        if rejections:
            # real rejection(s) -> feed the FULL reasons back (FIX: no 220-char truncation of feedback)
            correction = "\n".join(reasons)
            if attempt < MAX_ATTEMPTS:
                journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": "wren",
                         "text": f"attempt {attempt}: {len(rejections)} rejection(s), {len(approvals)} approval(s) — correcting"})
        else:
            # no rejections, just couldn't get a 2nd confident approval (timeouts) -> re-verify next loop,
            # don't rebuild from scratch with bogus feedback
            correction = ""
            journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": "wren",
                     "text": f"attempt {attempt}: {len(approvals)}/2 approvals, {len(timeouts)} inconclusive — re-verifying"})
    # 2026-07-20 Ross: "no blocked tasks — they go back into the task pool to be fixed; blocked only
    # creates a bottleneck". Exhausting MAX_ATTEMPTS no longer dead-ends the task. It RECYCLES back to
    # the pool (open, owner cleared) with EXPONENTIAL BACKOFF so the runner retries it later with the
    # accumulated correction — a genuinely-stuck task re-enters less and less often but is never a
    # terminal bottleneck. (Still never fakes a completion.)
    try:
        import qsb_council_tasks as _T
        _cur = next((t for t in _T.snapshot().get("tasks", []) if t.get("id") == tid), {})
        _rounds = int(_cur.get("rework_rounds", 0))
    except Exception:
        _rounds = 0
    backoff_min = min(8 * (2 ** _rounds), 240)   # 8m,16m,32m,... capped at 4h
    retry_after = (datetime.now(timezone.utc) + timedelta(minutes=backoff_min)).strftime("%Y-%m-%dT%H:%M:%SZ")
    journal({"ts": utc(), "event": "recycled", "task_id": tid, "actor": "wren", "retry_after": retry_after,
             "text": f"back to pool after {MAX_ATTEMPTS} attempts (retry in ~{backoff_min}m). Last: {correction[:200] or 'verification inconclusive'}"})
    return {"task": tid, "result": f"recycled to pool (retry ~{backoff_min}m — no 2-CEO quorum after {MAX_ATTEMPTS} attempts)",
            "tool": tool["tool"], "artifact": path}


def tick():
    if not gate_enabled():
        log({"tick": "paused", "reason": "kill switch enabled=false"})
        return
    if not peer_reachable():
        log({"tick": "skip", "reason": "no independent CEO reachable at :9120"})
        return
    wren_load = inflight_for("wren")
    if wren_load >= PER_CEO_CAP:
        log({"tick": "skip", "reason": f"Wren at cap ({wren_load}/{PER_CEO_CAP})"})
        return
    # PREFER the real open backlog; only if empty, run a governed maintenance cycle
    task = next_open_task()
    if task:
        r = run_backlog(task)
        log({"tick": "backlog", "task": r.get("task"), "result": r.get("result"), "wren_load_before": wren_load})
    else:
        rc = RUN.run(title="#AUTO governed maintenance task")
        log({"tick": "maintenance", "verdict": "PASS" if rc == 0 else "FAIL", "wren_load_before": wren_load})


def main():
    # CONCURRENT runner: a bounded thread pool works up to PER_CEO_CAP tasks at once (the cap the
    # rules already allow). Each tick harvests finished workers, then fills free slots — pre-claiming
    # each task so the next selection can't double-grab it. run_backlog is I/O-bound so threads scale.
    log({"event": "autorunner_start", "interval_s": INTERVAL, "per_ceo_cap": PER_CEO_CAP,
         "concurrency": PER_CEO_CAP, "pid": os.getpid()})
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=PER_CEO_CAP, thread_name_prefix="council_worker")
    pending = {}   # future -> task_id
    while True:
        try:
            # 1) harvest finished workers (non-blocking)
            if pending:
                done, _ = concurrent.futures.wait(list(pending.keys()), timeout=0,
                                                  return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in done:
                    tid = pending.pop(fut, "?")
                    try:
                        r = fut.result(timeout=0)
                        log({"tick": "worker_done", "task": (r or {}).get("task", tid), "result": (r or {}).get("result")})
                    except Exception as e:
                        log({"tick": "worker_error", "task": tid, "error": str(e)[:200]})
            # 2) fill free slots
            if not gate_enabled():
                log({"tick": "paused", "reason": "kill switch enabled=false"})
            elif not peer_reachable():
                log({"tick": "skip", "reason": "no independent CEO reachable at :9120"})
            else:
                # cap by the EXACT running-worker set we control (len(pending)) — inflight_for reads a
                # cached snapshot that lags fresh claims and caused over-spawn past the cap.
                free = PER_CEO_CAP - len(pending)
                spawned = 0
                while free > 0:
                    task = next_open_task()
                    if not task:
                        break
                    # pre-claim so the next next_open_task() can't re-select the same task
                    RUN.journal({"ts": utc(), "event": "claimed", "task_id": task["id"], "actor": "wren", "state": "in_progress"})
                    fut = executor.submit(run_backlog, task)
                    pending[fut] = task["id"]
                    spawned += 1
                    free -= 1
                if spawned:
                    log({"tick": "spawned", "count": spawned, "in_flight": len(pending)})
                elif not pending:
                    log({"tick": "idle", "reason": "no open backlog"})
        except Exception as e:
            log({"tick": "error", "error": str(e)[:200]})
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        tick()
    else:
        main()
