#!/usr/bin/env python3
"""
qsb_floor_activity_index.py — honest per-floor ACTIVITY INDEX for the QSB Tower.

Builds data/registries/qsb_floor_activity_index.json, an object keyed by floor id
("floor_0".."floor_170"). A floor is marked active:true ONLY when a REAL recent
signal (a registry/log/status file with a fresh mtime or last-row timestamp) can be
cited. Every floor gets an entry — quiet floors are honestly active:false, never
omitted.

HONESTY (R01): active:true always carries the real `source` path + `last_ts` it came
from, so it is independently verifiable. No guessing. mtime is only trusted for files
that are genuinely rewritten on refresh (status/stream/state files); for append-only
JSONL we prefer the last row's own timestamp field when present, else mtime.

Threshold: a signal counts as "fresh" (active) when age_s < FRESH_S (default 3600s).

READ-ONLY except the one output registry. No systemd install (a staged refresher
line is printed for Ross; wire it yourself if you want periodic regen).
"""
import json, os, sys, time, glob, re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(REPO, "data", "registries")
CANON = os.path.join(REG, "qsb_canonical_floor_registry_1_170.json")
OUT = os.path.join(REG, "qsb_floor_activity_index.json")

# PRIMARY per-floor signal: REAL WORKER TRAFFIC. tools/qsb_worker_activation_engine.py
# (owned by a sibling) wakes each floor's real assigned workers; every woken worker does a
# genuine deterministic read of its floor/room/station and posts a factual message here.
# A floor is active when its assigned workers have posted FRESH real rows. This is the
# honest signal that lights a floor + emits its train (R01: real worker traffic, not sims).
# Agreed schema (per row): a floor key in one of {floor_id | floor | station}, a worker id,
# a ts, and a message. Floor key may be the dir-slug ("floor_45_worker_recruitment_agency"),
# "floor_45", or a bare number — all resolved to a floor number below.
WORKER_ACTIVITY = os.path.join(REG, "qsb_floor_worker_activity.jsonl")

# FALLBACK per-floor signal: synthetic heartbeats (each real floor re-reads its own card).
# Used ONLY for floors that have a genuine function but NO fresh assigned-worker traffic,
# so we never fabricate and never double-count. Written by tools/qsb_floor_heartbeats.py.
HEARTBEATS = os.path.join(REG, "qsb_floor_heartbeats.jsonl")

# DIGITAL-TWIN DEPLOY signal (2026-07-30, Claude): the council ship-pipeline's apply-bridge writes a
# real audit row every time it changes a LIVE file (qsb_code_apply_audit.jsonl: target, sha, applied).
# When an applied change lands on a file that belongs to a floor (floors/floor_<n>_.../...), that floor
# genuinely just changed — so it lights on the twin/map, cited to the deploy audit. This is the honest
# data->twin link: a real gated deploy re-lights its floor (R01: cited, real, threshold-gated for age).
APPLY_AUDIT = os.path.join(REG, "qsb_code_apply_audit.jsonl")

FRESH_S = 3600  # < 1h = active

ISO = "%Y-%m-%dT%H:%M:%SZ"


def iso(ts):
    return time.strftime(ISO, time.gmtime(ts))


def last_row_ts(path):
    """Best-effort last-row timestamp (epoch) from a JSONL file's final non-empty line.
    Returns None if no parseable ts field found."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk = min(size, 65536)
            f.seek(size - chunk)
            tail = f.read().decode("utf-8", "replace")
    except Exception:
        return None
    for line in reversed([l for l in tail.splitlines() if l.strip()]):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        for k in ("ts", "timestamp", "time", "created", "created_at", "at", "t", "utc"):
            v = obj.get(k) if isinstance(obj, dict) else None
            if v is None:
                continue
            # numeric epoch
            if isinstance(v, (int, float)):
                return float(v) if v > 1e9 else None
            if isinstance(v, str):
                s = v.strip().replace("Z", "+00:00")
                for fmt in (None,):
                    try:
                        import datetime
                        return datetime.datetime.fromisoformat(s).timestamp()
                    except Exception:
                        pass
        return None
    return None


def signal(path, prefer_row_ts=False):
    """Return (age_s, last_ts_iso, abspath_rel) for a real existing file, else None.
    For JSONL with prefer_row_ts, use the last row's own ts when parseable."""
    ap = path if os.path.isabs(path) else os.path.join(REPO, path)
    if not os.path.exists(ap):
        return None
    now = time.time()
    ts = None
    if prefer_row_ts and ap.endswith(".jsonl"):
        ts = last_row_ts(ap)
    if ts is None:
        ts = os.path.getmtime(ap)
    rel = os.path.relpath(ap, REPO)
    return (int(max(0, now - ts)), iso(ts), rel)


def best(*candidates):
    """Given (path, signal_label[, prefer_row_ts]) tuples, return the freshest real one
    as (age_s, last_ts, source, signal_label) or None."""
    found = []
    for c in candidates:
        path, label = c[0], c[1]
        prefer = c[2] if len(c) > 2 else False
        s = signal(path, prefer)
        if s:
            found.append((s[0], s[1], s[2], label))
    if not found:
        return None
    found.sort(key=lambda x: x[0])
    return found[0]


# ---- Curated per-floor real signals. Each value is a list of (relpath, label, prefer_row_ts?)
# candidates; the FRESHEST existing one wins. Floors absent here fall through to
# generic per-floor-numbered file discovery below.
CURATED = {
    0:   [("data/registries/qsb_f0_calls.jsonl", "reception call log", True)],
    24:  [("data/registries/gene_pool_router_state.json", "gene-pool router state"),
          ("data/registries/gene_pool_router_live_events.jsonl", "gene-pool live events", True)],
    40:  [("data/registries/qsb_codex_autorunner_activity.jsonl", "codex autorunner activity", True)],
    41:  [("data/registries/qsb_oanda_tick_stream.jsonl", "OANDA live tick stream", True),
          ("data/registries/oanda_trading_floor_status.json", "OANDA floor status")],
    42:  [("data/registries/qsb_binance_tick_stream.jsonl", "Binance live tick stream", True),
          ("data/registries/binance_floor_status.json", "Binance floor status")],
    43:  [("data/registries/stock_floor_status.json", "stock floor status refresh"),
          ("data/registries/qsb_alpaca_tick_stream.jsonl", "Alpaca paper tick stream", True)],
    44:  [("data/registries/qsb_accounts_summary_latest.json", "accounts summary refresh"),
          ("data/registries/qsb_accounts_ledger.jsonl", "accounts ledger", True)],
    46:  [("data/registries/qsb_f46_team_runs.jsonl", "Wren bench team runs", True),
          ("data/registries/qsb_wren_dash_chat.jsonl", "Wren dash chat", True)],
    47:  [("data/registries/qsb_f47_team_records.jsonl", "F47 team records", True),
          ("data/registries/qsb_f47_records.jsonl", "F47 records", True)],
    48:  [("data/registries/qsb_floor48_lumen_ai_state.json", "Lumen AI state")],
    49:  [("data/registries/qsb_floor49_tower_studio_state.json", "Tower Studio state")],
    116: [("data/registries/qsb_floor116_quantum_activity.jsonl", "F116 real quantum-simulation jobs", True)],
    74:  [("data/registries/leadership_comms/room.jsonl", "town-square room chat", True)],
    75:  [("data/registries/qsb_council_tasks.jsonl", "council-of-15 tasks", True),
          ("data/registries/qsb_council_tasks_snapshot.json", "council tasks snapshot")],
    77:  [("data/registries/qsb_council_tasks.jsonl", "task-council tasks", True),
          ("data/registries/qsb_council_state_hash.json", "council state hash")],
    167: [("data/registries/qsb_boardroom_commentary.jsonl", "boardroom commentary", True),
          ("data/registries/leadership_comms/room.jsonl", "CEO room chat", True)],
    169: [("data/registries/qsb_tower_health_snapshot.json", "tower health snapshot (watchtower)"),
          ("data/registries/qsb_tower_activity_tail.jsonl", "tower activity tail", True)],
}

# Tower-wide operational signals that legitimately light the leadership/comms floors.
LEADERSHIP_FLOORS = {
    51: ("data/registries/leadership_comms/room.jsonl", "executive-council comms", True),
    50: ("data/registries/qsb_council_tasks.jsonl", "governance council tasks", True),
    52: ("data/registries/qsb_tower_health_snapshot.json", "infra-command health snapshot", False),
    53: ("data/registries/qsb_tower_health_snapshot.json", "tower-command health snapshot", False),
}


def load_heartbeats():
    """Scan the shared heartbeat log ONCE and return {floor_num:int -> (age_s, last_ts_iso,
    rel_source, signal_label)} for the freshest heartbeat row per floor. Honest: only rows
    with a real floor number and a parseable ts count; the freshest wins. Missing file -> {}."""
    if not os.path.exists(HEARTBEATS):
        return {}
    now = time.time()
    latest = {}  # floor -> (epoch_ts, iso_ts)
    try:
        with open(HEARTBEATS) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                fn = obj.get("floor")
                ts = obj.get("ts")
                if not isinstance(fn, int) or not isinstance(ts, str):
                    continue
                try:
                    import datetime
                    e = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if fn not in latest or e > latest[fn][0]:
                    latest[fn] = (e, ts)
    except Exception:
        return {}
    rel = os.path.relpath(HEARTBEATS, REPO)
    out = {}
    for fn, (e, ts) in latest.items():
        out[fn] = (int(max(0, now - e)), ts, rel, "floor heartbeat (real card re-read)")
    return out


def load_apply_deploys():
    """Scan the apply-bridge audit ONCE -> {floor_num:int -> (age_s, iso_ts, rel_source, label)} for
    the freshest APPLIED live change that maps to a floor (floors/floor_<n>_.../...). Honest: only rows
    with applied==true and a target that resolves to a floor number count; missing file -> {}. This is
    the data->twin link — a real gated deploy lights its floor, cited to the deploy audit row."""
    import datetime
    if not os.path.exists(APPLY_AUDIT):
        return {}
    now = time.time()
    latest = {}  # floor -> (epoch, iso)
    try:
        with open(APPLY_AUDIT) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict) or not obj.get("applied"):
                    continue
                tgt = obj.get("target") or ""
                m = re.match(r"floors/floor_?(\d+)", tgt)
                if not m:
                    continue
                fn = int(m.group(1))
                ts = obj.get("ts")
                if not isinstance(ts, str):
                    continue
                try:
                    e = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if fn not in latest or e > latest[fn][0]:
                    latest[fn] = (e, ts)
    except Exception:
        return {}
    rel = os.path.relpath(APPLY_AUDIT, REPO)
    return {fn: (int(max(0, now - e)), ts, rel, "live code deploy applied to this floor")
            for fn, (e, ts) in latest.items()}


def _floor_num_from_key(v):
    """Resolve a worker-activity floor key to an int floor number, honestly.
    Accepts an int, a bare-number string, 'floor_<n>', or a dir-slug like
    'floor_45_worker_recruitment_agency'. Returns int or None (never guesses beyond
    a leading floor_<n>/number pattern)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            return int(s)
        m = re.match(r"^floor[_\-]?(\d+)", s, re.I)
        if m:
            return int(m.group(1))
        m = re.match(r"^f(\d+)(?:_|$)", s, re.I)
        if m:
            return int(m.group(1))
    return None


def load_worker_activity():
    """Scan the real worker-traffic log ONCE -> {floor_num:int -> (age_s, last_ts_iso,
    rel_source, signal_label, worker_count)} for the freshest worker message per floor,
    counting DISTINCT workers seen recently on that floor. Honest: only rows resolving to a
    real floor number with a parseable ts count. Missing file -> {}. This is the PRIMARY
    signal; a floor is 'active' from here when its workers genuinely posted inside FRESH_S."""
    import datetime
    now = time.time()
    latest = {}        # floor -> (epoch, iso)
    workers = {}       # floor -> set(worker_id) within FRESH_S
    src_for = {}       # floor -> rel source path of its freshest row

    # The engine may write EITHER a shared log (WORKER_ACTIVITY) OR one file per floor
    # (qsb_floor_<n>_worker_activity.jsonl). Scan both — both are real worker traffic.
    paths = []
    if os.path.exists(WORKER_ACTIVITY):
        paths.append(WORKER_ACTIVITY)
    paths += sorted(glob.glob(os.path.join(REG, "qsb_floor_*_worker_activity.jsonl")))

    for path in paths:
        rel = os.path.relpath(path, REPO)
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    fn = None
                    for fk in ("floor_id", "floor", "floor_num", "floor_number", "station"):
                        fn = _floor_num_from_key(obj.get(fk))
                        if fn is not None:
                            break
                    if fn is None:
                        continue
                    ts = obj.get("ts") or obj.get("timestamp") or obj.get("time")
                    if not isinstance(ts, str):
                        continue
                    try:
                        e = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        continue
                    if fn not in latest or e > latest[fn][0]:
                        latest[fn] = (e, ts)
                        src_for[fn] = rel
                    if (now - e) < FRESH_S:
                        wid = obj.get("worker_id") or obj.get("worker") or obj.get("wid")
                        if wid:
                            workers.setdefault(fn, set()).add(wid)
        except Exception:
            continue

    out = {}
    for fn, (e, ts) in latest.items():
        wc = len(workers.get(fn, ()))
        label = (f"{wc} assigned worker{'s' if wc != 1 else ''} active"
                 if wc else "assigned-worker activity")
        out[fn] = (int(max(0, now - e)), ts, src_for.get(fn, ""), label, wc)
    return out


def generic_floor_signal(num):
    """Discover a per-floor-numbered registry file (qsb_fNN_*, qsb_floorNNN_*, *floor_NN*)
    and return the freshest as a signal, or None. Prefers .jsonl last-row ts."""
    pats = [
        os.path.join(REG, f"qsb_f{num}_*.json*"),
        os.path.join(REG, f"qsb_floor{num}_*.json*"),
        os.path.join(REG, f"qsb_floor_{num}_*.json*"),
        os.path.join(REG, f"*floor_{num}_*.json*"),
        os.path.join(REG, f"*floor{num}_*.json*"),
    ]
    cands = []
    seen = set()
    for p in pats:
        for hit in glob.glob(p):
            if hit in seen:
                continue
            seen.add(hit)
            bn = os.path.basename(hit)
            if ".bak" in bn or "PRE_REPAIR" in bn or "reconcil" in bn.lower():
                continue
            # avoid matching floor1 when num==1 hitting floor10..; enforce word boundary
            if not re.search(rf"(^|[_/])f(loor_?)?{num}(_|\.|$)", bn):
                continue
            cands.append((os.path.relpath(hit, REPO), f"floor-{num} state file",
                          hit.endswith(".jsonl")))
    return best(*cands) if cands else None


def main():
    with open(CANON) as f:
        canon = json.load(f)
    floors = canon.get("floors", {})
    # floor 0 recorded separately in canon
    labels = {0: canon.get("floor_0", {}).get("label", "Reception Lobby")}
    for n, meta in floors.items():
        labels[int(n)] = meta.get("label", f"Floor {n}")

    # PRIMARY: real worker traffic per floor (freshest woken-worker message).
    worker_act = load_worker_activity()
    # FALLBACK: synthetic card-read heartbeats (only where no fresh worker traffic).
    heartbeats = load_heartbeats()
    # DIGITAL-TWIN link: freshest applied live deploy per floor (competes on freshness below).
    deploys = load_apply_deploys()

    index = {}
    active_count = 0
    active_examples = []

    for num in range(0, 171):
        label = labels.get(num, f"Floor {num}")
        disp = f"F{num} · {label}"
        sig = None

        # SIGNAL PRIORITY (all real, all cited):
        #   1. REAL WORKER TRAFFIC — a floor's assigned workers genuinely posted (PRIMARY).
        #   2. curated richer live signal (trading/comms/council) for the hub floors.
        #   3. generic per-floor state registry discovery.
        #   4. synthetic card-read heartbeat — FALLBACK only, never overrides 1-3 when
        #      those are fresher, and exists solely so a genuinely-functional floor with no
        #      assigned-worker traffic yet still reads honestly-active from its own card.
        # Whichever REAL cited signal is actually freshest wins; nothing is invented, and
        # a heartbeat never double-counts a floor that already lit from real worker traffic.
        wa = worker_act.get(num)
        if wa is not None:
            # worker-activity tuple is (age, ts, src, label, worker_count) — trim to 4.
            sig = wa[:4]
        if sig is None and num in CURATED:
            sig = best(*CURATED[num])
        if sig is None and num in LEADERSHIP_FLOORS:
            p, lbl, prefer = LEADERSHIP_FLOORS[num]
            sig = best((p, lbl, prefer))
        if sig is None:
            sig = generic_floor_signal(num)
        # FALLBACK heartbeat: only consider it if there is NO fresh worker traffic for this
        # floor (avoids double-counting). It wins over a stale curated/generic signal only.
        if wa is None:
            hb = heartbeats.get(num)
            if hb is not None and (sig is None or hb[0] < sig[0]):
                sig = hb
        # DIGITAL-TWIN link: a real gated deploy to this floor lights it, cited to the apply audit.
        # Competes on freshness — wins only when it is the freshest real cited signal for the floor.
        dp = deploys.get(num)
        if dp is not None and (sig is None or dp[0] < sig[0]):
            sig = dp

        fid = f"floor_{num}"
        if sig is not None:
            age_s, last_ts, source, signal_label = sig
            active = age_s < FRESH_S
            index[fid] = {
                "active": active,
                "last_ts": last_ts,
                "age_s": age_s,
                "source": source,
                "label": disp,
                "signal": signal_label,
            }
            if active:
                active_count += 1
                active_examples.append((num, disp, age_s, source, signal_label))
        else:
            index[fid] = {
                "active": False,
                "last_ts": None,
                "age_s": None,
                "source": None,
                "label": disp,
                "signal": "none",
            }

    now = time.time()
    out = {
        "schema": "qsb_floor_activity_index_v1",
        "generated_ts": iso(now),
        "generated_epoch": int(now),
        "threshold_s": FRESH_S,
        "threshold_note": f"active:true iff a real cited signal has age_s < {FRESH_S}s",
        "total_floors": len(index),
        "active_floors": active_count,
        "honesty": "R01: every active:true carries a verifiable source path + last_ts; "
                   "quiet floors are active:false (never omitted). mtime trusted only for "
                   "rewritten status/stream/state files; JSONL prefers last-row ts.",
        "floors": index,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)

    # Console proof
    print(f"[qsb_floor_activity_index] wrote {os.path.relpath(OUT, REPO)}")
    print(f"  {active_count} of {len(index)} floors ACTIVE (threshold < {FRESH_S}s)")
    for num, disp, age_s, source, signal_label in sorted(active_examples):
        print(f"  ACTIVE floor_{num:<3} {disp:<40} age={age_s:>5}s  {signal_label}  <- {source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
