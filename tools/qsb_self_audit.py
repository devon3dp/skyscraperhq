#!/usr/bin/env python3
"""
qsb_self_audit.py — CONTINUOUS TOWER SELF-AUDIT LOOP
=====================================================

Runs cheap, REAL, read-only health/consistency probes across the SkyscraperHQ
tower every ~15min (via qsb-self-audit.timer). For every GENUINE problem it
finds, it books a task on the council board (tag `self_audit`) and appends an
evidence row to data/registries/qsb_self_audit_findings.jsonl so the tower's
own repair pipeline (Codex / council) can pick it up.

Design contract (hard):
  * READ-ONLY probes. This tool NEVER fixes anything and NEVER restarts
    anything. It finds + queues; the gated repair pipeline fixes.
  * HONEST. It only queues problems that are really present, each with the
    actual probe evidence. When everything is clean it says so and queues
    nothing.
  * DEDUP. The same problem is not re-queued every 15min. A finding has a
    stable `key`; an open finding for that key suppresses re-queue. It only
    re-opens if the problem PERSISTS past a re-alert window or WORSENS
    (severity escalates).

Checks performed (all real, all cheap):
  1. systemd services failed / crash-looping (activating-restart churn)
  2. dashboards returning non-200 or empty body
  3. wedged Ollama (a small model probe that times out / errors)
  4. stale registries that SHOULD be fresh (age past a per-file budget)
  5. workers that stopped logging (belief-trader fleet + tower activity tail)
  6. map trains: moving != len(trains) on the live transit map
  7. tasks stuck in-progress/claimed past a timeout
  8. root disk > 90%
  9. gene-pool providers newly dead (needs_new_key set grew)

Usage:
  python3 tools/qsb_self_audit.py            # run one audit pass
  python3 tools/qsb_self_audit.py --dry-run  # probe + print, queue nothing
  python3 tools/qsb_self_audit.py --json     # machine-readable summary
"""
import argparse, json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "data", "registries")
FINDINGS = os.path.join(REG, "qsb_self_audit_findings.jsonl")
sys.path.insert(0, os.path.join(ROOT, "tools"))

# Re-alert only after a finding has persisted this long since last queued.
REALERT_SEC = 6 * 3600          # 6h: don't spam the board every 15min
# Severity ranking for "worsened" detection.
SEV_RANK = {"info": 0, "amber": 1, "red": 2}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sh(cmd, t=6):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=t).stdout.strip()
    except Exception:
        return ""


def _http(url, timeout=3.0):
    """Return (status_code, body_len, err). Read-only GET."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qsb-self-audit"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, len(body), None
    except urllib.error.HTTPError as e:
        return e.code, 0, None
    except Exception as e:
        return None, 0, str(e)[:120]


def _age(path):
    try:
        return time.time() - os.path.getmtime(path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CHECKS  — each returns a list of finding dicts:
#   {key, severity, title, detail, evidence}
# key must be STABLE for a given problem so dedup works.
# ---------------------------------------------------------------------------

def check_services():
    out = []
    # Failed units.
    failed = _sh("systemctl list-units 'qsb-*' --state=failed --no-legend --plain "
                 "2>/dev/null | awk '{print $1}'")
    for unit in [u for u in failed.splitlines() if u.strip()]:
        detail = _sh(f"systemctl show {unit} -p Result -p NRestarts --value 2>/dev/null").replace("\n", " ")
        out.append({
            "key": f"svc_failed:{unit}",
            "severity": "red",
            "title": f"Service failed: {unit}",
            "detail": f"{unit} is in failed state",
            "evidence": f"systemctl is-active={_sh(f'systemctl is-active {unit}')}; {detail}",
        })
    # Crash-looping: high restart churn while activating (auto-restart thrash).
    churn = _sh("systemctl list-units 'qsb-*' --no-legend --plain 2>/dev/null "
                "| awk '$4==\"auto-restart\"||$4==\"activating\"{print $1}'")
    for unit in [u for u in churn.splitlines() if u.strip()]:
        n = _sh(f"systemctl show {unit} -p NRestarts --value 2>/dev/null")
        try:
            n_i = int(n)
        except Exception:
            n_i = 0
        if n_i >= 5:
            out.append({
                "key": f"svc_crashloop:{unit}",
                "severity": "red",
                "title": f"Service crash-looping: {unit}",
                "detail": f"{unit} auto-restarting, NRestarts={n_i}",
                "evidence": f"NRestarts={n_i}; sub-state via list-units=auto-restart/activating",
            })
    return out


# Dashboards that should answer 200 with a non-empty body. Only probe ports
# that are actually meant to be live HTTP dashboards.
DASH = {
    8848: "Lumen (F48)",
    8849: "Tower Studio (F49)",
    8854: "Tour Guide",
    8860: "Brain Router V4 / Mission Control",
    8863: "Agentic Traders Dash",
    8875: "Tower Transit Map",
}


def check_dashboards():
    out = []
    for port, name in DASH.items():
        # Skip ports that aren't even bound — that's a service check concern,
        # not a "dashboard returned bad HTTP" concern (avoids false doubles).
        bound = _sh(f"ss -ltn 2>/dev/null | grep -c ':{port} '")
        if bound in ("", "0"):
            continue
        code, blen, err = _http(f"http://127.0.0.1:{port}/")
        if code is None:
            out.append({
                "key": f"dash_down:{port}",
                "severity": "red",
                "title": f"Dashboard unreachable: {name} :{port}",
                "detail": f"{name} bound on :{port} but GET / failed",
                "evidence": f"error={err}",
            })
        elif code != 200:
            out.append({
                "key": f"dash_http:{port}",
                "severity": "amber",
                "title": f"Dashboard non-200: {name} :{port} -> {code}",
                "detail": f"{name} returned HTTP {code}",
                "evidence": f"GET http://127.0.0.1:{port}/ status={code}",
            })
        elif blen == 0:
            out.append({
                "key": f"dash_empty:{port}",
                "severity": "amber",
                "title": f"Dashboard empty body: {name} :{port}",
                "detail": f"{name} returned 200 but zero-length body",
                "evidence": f"GET http://127.0.0.1:{port}/ status=200 len=0",
            })
    return out


def check_ollama():
    """A 1-token probe against a small loaded model. If a model is loaded but
    the probe times out, ollama is wedged."""
    out = []
    if not _sh("which ollama"):
        return out
    # Which models are currently LOADED into memory (ollama ps).
    ps = _sh("ollama ps 2>/dev/null")
    loaded = [ln.split()[0] for ln in ps.splitlines()[1:] if ln.strip()]
    # Pick a probe target: a loaded model if any, else a small on-disk one.
    target = None
    if loaded:
        target = loaded[0]
    else:
        lst = _sh("ollama list 2>/dev/null")
        for ln in lst.splitlines()[1:]:
            name = ln.split()[0] if ln.strip() else ""
            if any(s in name for s in ("llama3.2", "mistral", "neural-chat")):
                target = name
                break
    if not target:
        return out
    t0 = time.time()
    # num_predict:1 keeps it to a single token; short timeout.
    payload = json.dumps({"model": target, "prompt": "hi",
                          "stream": False, "options": {"num_predict": 1}})
    code, _blen, err = None, 0, None
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                     data=payload.encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
            code = r.status
    except Exception as e:
        err = str(e)[:120]
    dt = round(time.time() - t0, 1)
    if code != 200:
        sev = "red" if target in loaded else "amber"
        out.append({
            "key": f"ollama_wedged:{target}",
            "severity": sev,
            "title": f"Ollama wedged: {target} 1-token probe failed",
            "detail": f"model {target} ({'loaded' if target in loaded else 'on-disk'}) "
                      f"did not answer a 1-token probe in {dt}s",
            "evidence": f"POST /api/generate num_predict=1 -> code={code} err={err} elapsed={dt}s",
        })
    return out


# Registries that SHOULD be refreshed by their own timers/loops. key -> max age (s).
FRESH_BUDGET = {
    "qsb_tower_activity_tail.jsonl": 30 * 60,       # tower heartbeat/activity
    "qsb_gene_pool_key_health.json": 60 * 60,       # key-health timer (15min)
    "qsb_council_tasks.jsonl": 6 * 3600,            # council board activity
}


def check_stale_registries():
    out = []
    for fn, budget in FRESH_BUDGET.items():
        p = os.path.join(REG, fn)
        if not os.path.exists(p):
            out.append({
                "key": f"reg_missing:{fn}",
                "severity": "amber",
                "title": f"Registry missing: {fn}",
                "detail": f"expected registry {fn} does not exist",
                "evidence": f"path {p} not found",
            })
            continue
        age = _age(p)
        if age is not None and age > budget:
            out.append({
                "key": f"reg_stale:{fn}",
                "severity": "amber",
                "title": f"Registry stale: {fn}",
                "detail": f"{fn} last modified {int(age/60)}min ago "
                          f"(budget {int(budget/60)}min)",
                "evidence": f"mtime_age={int(age)}s budget={budget}s path={p}",
            })
    return out


def check_workers():
    """Belief-trader fleet alive + logging. If systemd says N traders but the
    process count is far lower, or the shared activity tail stopped growing."""
    out = []
    # Count enabled/active belief-trader units vs live processes.
    active_units = _sh("systemctl list-units 'qsb-belief-trader@*' --state=active "
                       "--no-legend --plain 2>/dev/null | wc -l")
    procs = _sh("ps -eo cmd ww 2>/dev/null | grep -c '[b]elief_driven_trader.py'")
    try:
        au, pc = int(active_units), int(procs)
    except Exception:
        au, pc = 0, 0
    if au >= 5 and pc < au // 2:
        out.append({
            "key": "workers_missing:belief_traders",
            "severity": "red",
            "title": f"Belief-trader fleet degraded: {pc} procs vs {au} active units",
            "detail": f"systemd reports {au} active belief-trader units but only "
                      f"{pc} python processes are running",
            "evidence": f"active_units={au} live_procs={pc}",
        })
    return out


def check_map_trains():
    """Live transit map: moving must equal len(trains)."""
    out = []
    bound = _sh("ss -ltn 2>/dev/null | grep -c ':8875 '")
    if bound in ("", "0"):
        return out
    try:
        req = urllib.request.Request("http://127.0.0.1:8875/api/data",
                                     headers={"User-Agent": "qsb-self-audit"})
        with urllib.request.urlopen(req, timeout=4) as r:
            d = json.loads(r.read())
    except Exception:
        return out  # dashboards check already covers unreachable
    trains = d.get("trains", [])
    moving = d.get("moving")
    if moving is not None and moving != len(trains):
        out.append({
            "key": "map_trains_mismatch",
            "severity": "amber",
            "title": f"Map train count mismatch: moving={moving} len(trains)={len(trains)}",
            "detail": "transit map `moving` counter disagrees with actual train array length",
            "evidence": f"/api/data moving={moving} len(trains)={len(trains)}",
        })
    return out


def check_stuck_tasks(timeout_sec=24 * 3600):
    """Tasks in claimed/in_progress with no activity past timeout."""
    out = []
    try:
        import qsb_council_tasks as T
        tasks = T.snapshot().get("tasks", [])
    except Exception as e:
        return [{
            "key": "council_snapshot_error",
            "severity": "amber",
            "title": "Council snapshot failed",
            "detail": "could not read council board to audit stuck tasks",
            "evidence": str(e)[:160],
        }]
    now = time.time()

    def _ts(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    for t in tasks:
        if t.get("state") not in ("claimed", "in_progress"):
            continue
        # Last-activity = max of any timestamp we have on the task.
        cands = [_ts(t.get("claimed_at")), _ts(t.get("started_at")),
                 _ts(t.get("assigned_at")), _ts(t.get("created_at"))]
        hist = t.get("history") or []
        for h in hist:
            if isinstance(h, dict):
                cands.append(_ts(h.get("ts") or h.get("at")))
        cands = [c for c in cands if c]
        if not cands:
            continue
        last = max(cands)
        stuck = now - last
        if stuck > timeout_sec:
            out.append({
                "key": f"task_stuck:{t.get('id')}",
                "severity": "amber",
                "title": f"Task stuck {int(stuck/3600)}h: {(t.get('title') or '')[:60]}",
                "detail": f"task {t.get('id')} state={t.get('state')} no activity for "
                          f"{int(stuck/3600)}h (owner={t.get('owner') or t.get('claimed_by')})",
                "evidence": f"id={t.get('id')} state={t.get('state')} "
                            f"last_activity_age={int(stuck)}s timeout={timeout_sec}s",
            })
    return out


def check_disk():
    out = []
    pct = _sh("df -P / | awk 'NR==2{print $5}'").rstrip("%")
    try:
        p = int(pct)
    except Exception:
        return out
    if p > 90:
        out.append({
            "key": "disk_root_full",
            "severity": "red" if p >= 95 else "amber",
            "title": f"Root disk {p}% full",
            "detail": f"/ is at {p}% — over the 90% threshold",
            "evidence": _sh("df -Ph / | tail -1"),
        })
    return out


def check_gene_pool(persist=True):
    """Compare current needs_new_key set against last audited snapshot; flag
    providers that newly went dead. `persist` controls whether we advance the
    comparison baseline (skipped on --dry-run so a dry pass doesn't hide a
    genuinely-new death from the next real run)."""
    out = []
    p = os.path.join(REG, "qsb_gene_pool_key_health.json")
    if not os.path.exists(p):
        return out
    try:
        d = json.load(open(p))
    except Exception:
        return out
    dead_now = set(d.get("needs_new_key", []))
    # Read the last dead-set we recorded from our own findings state file.
    state_p = os.path.join(REG, "qsb_self_audit_state.json")
    prev = {}
    if os.path.exists(state_p):
        try:
            prev = json.load(open(state_p))
        except Exception:
            prev = {}
    dead_prev = set(prev.get("gene_pool_dead", []))
    newly_dead = dead_now - dead_prev
    # Persist current set for next run's comparison (real runs only).
    if persist:
        prev["gene_pool_dead"] = sorted(dead_now)
        prev["gene_pool_dead_ts"] = _utc()
        try:
            json.dump(prev, open(state_p, "w"), indent=1)
        except Exception:
            pass
    if newly_dead:
        out.append({
            "key": f"gene_pool_dead:{','.join(sorted(newly_dead))}",
            "severity": "amber",
            "title": f"Gene-pool provider(s) newly dead: {', '.join(sorted(newly_dead))}",
            "detail": f"providers newly flagged needs_new_key: {sorted(newly_dead)}",
            "evidence": f"needs_new_key now={sorted(dead_now)} was={sorted(dead_prev)}",
        })
    return out


CHECKS = [
    check_services, check_dashboards, check_ollama, check_stale_registries,
    check_workers, check_map_trains, check_stuck_tasks, check_disk,
    check_gene_pool,
]


# ---------------------------------------------------------------------------
# DEDUP + QUEUE
# ---------------------------------------------------------------------------

def _load_findings():
    rows = []
    if os.path.exists(FINDINGS):
        with open(FINDINGS) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return rows


def _open_state_by_key(rows):
    """Return {key: last_row} using latest event per key. A key is 'open' if its
    most recent event is not `resolved`."""
    latest = {}
    for r in rows:
        k = r.get("key")
        if not k:
            continue
        latest[k] = r  # rows are append-only in time order
    return latest


def _append_finding(row):
    with open(FINDINGS, "a") as f:
        f.write(json.dumps(row) + "\n")


def _book_task(finding):
    """Book a council task, tag self_audit. Returns task_id or None."""
    try:
        import qsb_council_tasks as T
        res = T.create(
            title=f"[self_audit] {finding['title']}",
            description=(finding.get("detail", "") + "\n\nProbe evidence: "
                         + finding.get("evidence", "")
                         + f"\n\nfinding_key: {finding['key']}"
                         + "\n(auto-filed by tools/qsb_self_audit.py — read-only "
                           "audit; repair pipeline fixes under the gate)"),
            actor="self_audit",
            priority="high" if finding.get("severity") == "red" else "normal",
            tags=["self_audit", finding.get("severity", "amber")],
        )
        return res.get("task_id")
    except Exception as e:
        return f"ERR:{str(e)[:80]}"


def run(dry_run=False):
    ts = _utc()
    found = []
    for chk in CHECKS:
        try:
            if chk is check_gene_pool:
                found.extend(chk(persist=not dry_run) or [])
            else:
                found.extend(chk() or [])
        except Exception as e:
            found.append({
                "key": f"check_error:{chk.__name__}",
                "severity": "info",
                "title": f"Self-audit check errored: {chk.__name__}",
                "detail": "an audit probe itself raised — investigate the probe",
                "evidence": str(e)[:160],
            })

    prev_rows = _load_findings()
    open_state = _open_state_by_key(prev_rows)

    queued, suppressed = [], []
    for fnd in found:
        key = fnd["key"]
        last = open_state.get(key)
        do_queue = True
        reason = "new"
        if last and last.get("status") in ("open", "requeued"):
            # Already open. Suppress unless persisted past re-alert window OR worsened.
            last_ts = last.get("ts", "")
            try:
                last_epoch = datetime.fromisoformat(last_ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                last_epoch = 0
            age = time.time() - last_epoch
            worsened = SEV_RANK.get(fnd["severity"], 0) > SEV_RANK.get(last.get("severity"), 0)
            if worsened:
                reason = "worsened"
            elif age > REALERT_SEC:
                reason = "persisted"
            else:
                do_queue = False

        row = {
            "ts": ts, "key": key, "severity": fnd["severity"],
            "title": fnd["title"], "detail": fnd["detail"],
            "evidence": fnd["evidence"],
        }
        if do_queue and not dry_run:
            tid = _book_task(fnd)
            row["status"] = "requeued" if reason in ("persisted", "worsened") else "open"
            row["reason"] = reason
            row["task_id"] = tid
            _append_finding(row)
            queued.append(row)
        elif do_queue and dry_run:
            row["status"] = "would_queue"
            row["reason"] = reason
            queued.append(row)
        else:
            suppressed.append({"key": key, "severity": fnd["severity"],
                               "title": fnd["title"], "reason": "dedup_open_recent"})

    return {"ts": ts, "checks": len(CHECKS), "found": len(found),
            "queued": queued, "suppressed": suppressed,
            "clean": len(found) == 0}


def main():
    ap = argparse.ArgumentParser(description="Continuous tower self-audit (read-only, queue-only).")
    ap.add_argument("--dry-run", action="store_true", help="probe + print, queue nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    res = run(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(res, indent=1))
        return

    print(f"=== QSB SELF-AUDIT {res['ts']} ===")
    print(f"checks run: {res['checks']}   real problems found: {res['found']}")
    if res["clean"]:
        print("CLEAN — every probe passed. Nothing queued.")
        return
    if res["queued"]:
        verb = "WOULD queue" if args.dry_run else "QUEUED"
        print(f"\n{verb} ({len(res['queued'])}):")
        for r in res["queued"]:
            tid = r.get("task_id", "")
            print(f"  [{r['severity']:>5}] {r['title']}")
            print(f"          evidence: {r['evidence']}")
            print(f"          reason={r.get('reason')} task={tid}")
    if res["suppressed"]:
        print(f"\nSUPPRESSED as still-open (dedup) ({len(res['suppressed'])}):")
        for r in res["suppressed"]:
            print(f"  [{r['severity']:>5}] {r['title']}  ({r['reason']})")


if __name__ == "__main__":
    main()
