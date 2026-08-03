#!/usr/bin/env python3
"""
qsb_worker_chain_reporting.py — CHAIN-OF-COMMAND reporting path for the QSB Tower.

Floor leads collect their floor's REAL worker/floor state, roll it into a concise
per-floor report (counts, notable real facts, genuine NEEDS), and post that report
UP the chain — ultimately to Wren (via her REAL leadership-comms inbox queue, which
her live :8855 client drains) with a copy to Codex.

R01 / NO SIMS — HARD RULE
  Every number, fact, and NEED in every report is derived DETERMINISTICALLY from a
  real on-disk source with a citable path + timestamp. Nothing is invented. A NEED
  is emitted ONLY when the underlying real data genuinely shows one (stale per-floor
  registry, gate locked, no fresh floor heartbeat, empty worker-activity, etc.). If a
  floor has no real signal it is reported honestly as "quiet / no fresh signal" — it
  does not get a fabricated status.

WHERE THE REAL DATA COMES FROM (read-only; we never write these):
  1. data/registries/qsb_worker_chain_of_command.json
       the hierarchy — who reports to whom; gives us the real floor lead per floor.
  2. data/registries/qsb_floor_heartbeats.jsonl        (sibling: qsb_floor_heartbeats.py)
       per-floor real card re-read: roster size/categories, floor_manager, zone,
       gate_execution_allowed, per_floor_registries, freshness. This is each floor's
       own honest "voice".
  3. data/registries/qsb_floor_activity_index.json     (sibling: qsb_floor_activity_index.py)
       per-floor active:true/false with the real source + last_ts + age_s it came from.
  4. data/registries/qsb_floor_worker_activity/<floor>.jsonl   (sibling: qsb_worker_activation_engine.py)
       OR data/registries/qsb_floor_worker_activity.jsonl (single-file variant) —
       real per-worker messages posted by the activation engine. Consumed when present;
       if the engine has not produced data yet we note that honestly and roll up from
       (2)+(3) alone. Validated once its data flows.
  5. data/registries/qsb_floor_intercom_state.json / _packets_latest.json
       real sealed-packet intercom traffic per floor (lift-routed).

WHERE THE REPORTS GO (real channels, no impersonation, no vault, no auth flip):
  - Wren: appended to data/registries/leadership_comms/queues/wren.jsonl — this IS
    Wren's real inbox. The live qsb-leadership-relay :8855 drains it via /inbox to her
    running client, which prints + acks it and moves it to delivered/wren.jsonl. The
    message `from` field is "chain_reporting" (an honest sender label — NOT Wren, NOT a
    CEO, so nobody is impersonated). msg_id is a stable hash so re-runs de-dupe.
  - Codex: appended to data/registries/qsb_codex_autorunner_activity.jsonl (Codex's own
    real activity log that his autorunner reads) AND to our own copy registry.
  - Audit / rollup: data/registries/qsb_worker_chain_reports.jsonl (append-only, our own).

VOLUME BOUND: one rolled-up report per ACTIVE floor per run (dozens, not ~2000
individual worker messages). Quiet floors are summarised in a single tail line.

Optional bounded LLM: --llm-summaries turns each per-floor deterministic report into a
one-sentence lead summary via the existing consult path (tools/qsb_consult_external.py),
respecting its $1/day cap. OFF by default; deterministic rollups are preferred and are
what ship. Capped to --llm-max floors (default 6) so we never fan out per worker.

No execution. No gate flips. No writes outside our own registry + Wren's inbox queue +
Codex's activity log (all append-only).

USAGE:
  python3 tools/qsb_worker_chain_reporting.py --once           # one full cycle, deliver
  python3 tools/qsb_worker_chain_reporting.py --once --dry     # compute + print, no deliver
  python3 tools/qsb_worker_chain_reporting.py --once --floor 1 # single floor (proof)
  python3 tools/qsb_worker_chain_reporting.py --once --llm-summaries --llm-max 4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
COMMS = REG / "leadership_comms"

# --- real inputs (read-only) ---
CHAIN = REG / "qsb_worker_chain_of_command.json"
HEARTBEATS = REG / "qsb_floor_heartbeats.jsonl"
ACTIVITY_INDEX = REG / "qsb_floor_activity_index.json"
INTERCOM_STATE = REG / "qsb_floor_intercom_state.json"
# per-floor worker activity (sibling qsb_worker_activation_engine.py). Its real layout
# is one file per floor: data/registries/qsb_floor_<n>_worker_activity.jsonl, each row
# a real worker_floor_report {ts, floor, worker_id, room, station, roster_size,
# floor_manager, need, message}. A durable cross-floor tail also exists.
def _worker_act_path(floor: int) -> Path:
    return REG / f"qsb_floor_{floor}_worker_activity.jsonl"


WORKER_BUS_TAIL = REG / "qsb_worker_bus_activity.jsonl"      # durable cross-floor tail
# legacy fallbacks (older layouts) kept for resilience:
WORKER_ACT_DIR = REG / "qsb_floor_worker_activity"
WORKER_ACT_SINGLE = REG / "qsb_floor_worker_activity.jsonl"

# --- real outputs (append-only) ---
WREN_INBOX = COMMS / "queues" / "wren.jsonl"                 # Wren's REAL inbox queue
CODEX_ACT = REG / "qsb_codex_autorunner_activity.jsonl"      # Codex's REAL activity log
CHAIN_REPORTS = REG / "qsb_worker_chain_reports.jsonl"       # our own audit/rollup registry
F47_RECORDS = REG / "qsb_f47_team_records.jsonl"

CONSULT_TOOL = ROOT / "tools" / "qsb_consult_external.py"

FRESH_S = 3600          # a floor signal is "fresh" if younger than this
HEARTBEAT_STALE_S = 900  # a floor lead is "silent" if its last heartbeat is older than this


def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _iter_jsonl(p: Path):
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip().lstrip("\x00")
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except OSError:
        return


def _append_jsonl(p: Path, row: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _age_s(ts_iso: str) -> float | None:
    if not ts_iso:
        return None
    # robust ISO-8601 parse (handles Z, ±offset, microseconds — covers both the sibling
    # engine's "...+00:00" rows and the heartbeat's "...Z" rows).
    s = ts_iso.strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# 1. Chain of command → per-floor lead + roster count
# ---------------------------------------------------------------------------
def load_chain() -> dict:
    """Return {floor:int -> {'lead_worker_id', 'lead_role', 'team', 'workers':[ids],
    'n_workers':int}} built from the REAL chain-of-command registry."""
    d = _read_json(CHAIN, {})
    out: dict[int, dict] = {}
    for w in d.get("chain", []):
        fl = w.get("floor")
        if fl is None:
            continue
        e = out.setdefault(fl, {"lead_worker_id": None, "lead_role": None,
                                "team": w.get("team"), "workers": []})
        e["workers"].append(w.get("worker_id"))
        # the floor lead is the FLOOR_OWNER (else the FLOOR_MANAGER) per this floor
        if w.get("manager_role_key") == "FLOOR_OWNER" and not e["lead_worker_id"]:
            e["lead_worker_id"] = w.get("worker_id")
            e["lead_role"] = w.get("role")
    # fall back to FLOOR_MANAGER as lead where no owner named
    for w in d.get("chain", []):
        fl = w.get("floor")
        if fl in out and not out[fl]["lead_worker_id"] and w.get("manager_role_key") == "FLOOR_MANAGER":
            out[fl]["lead_worker_id"] = w.get("worker_id")
            out[fl]["lead_role"] = w.get("role")
    for e in out.values():
        e["n_workers"] = len(e["workers"])
    return out


# ---------------------------------------------------------------------------
# 2. Latest real heartbeat per floor (the floor lead's own honest re-read)
# ---------------------------------------------------------------------------
def latest_heartbeats() -> dict[int, dict]:
    latest: dict[int, dict] = {}
    for row in _iter_jsonl(HEARTBEATS):
        fl = row.get("floor")
        if fl is None:
            continue
        prev = latest.get(fl)
        if prev is None or row.get("ts", "") >= prev.get("ts", ""):
            latest[fl] = row
    return latest


# ---------------------------------------------------------------------------
# 3. Activity index per floor (active/stale with real source)
# ---------------------------------------------------------------------------
def activity_index() -> dict[int, dict]:
    d = _read_json(ACTIVITY_INDEX, {})
    floors = d.get("floors", {}) if isinstance(d, dict) else {}
    out: dict[int, dict] = {}
    for k, v in floors.items():
        try:
            fl = int(k.split("_")[1])
        except Exception:
            continue
        out[fl] = v
    return out


# ---------------------------------------------------------------------------
# 4. Per-floor worker activity from the sibling activation engine (if present)
# ---------------------------------------------------------------------------
def worker_activity(floor: int) -> dict:
    """Return {'n_msgs':int, 'fresh':bool, 'last_ts':str|None, 'needs':[str], 'source':str|None}
    from the sibling's real per-floor worker activity. Honest empty result if the
    activation engine hasn't produced data yet."""
    rows: list[dict] = []
    src = None
    perfloor = _worker_act_path(floor)                 # sibling's real layout
    if perfloor.exists():
        rows = list(_iter_jsonl(perfloor)); src = str(perfloor.relative_to(ROOT))
    elif (WORKER_ACT_DIR / f"floor_{floor}.jsonl").exists():   # legacy fallback
        p = WORKER_ACT_DIR / f"floor_{floor}.jsonl"
        rows = list(_iter_jsonl(p)); src = str(p.relative_to(ROOT))
    elif WORKER_ACT_SINGLE.exists():                   # legacy single-file fallback
        for r in _iter_jsonl(WORKER_ACT_SINGLE):
            if r.get("floor") == floor:
                rows.append(r)
        if rows:
            src = str(WORKER_ACT_SINGLE.relative_to(ROOT))
    if not rows:
        return {"n_msgs": 0, "fresh": False, "last_ts": None, "needs": [], "source": None}
    last_ts = max((r.get("ts", "") for r in rows), default="")
    age = _age_s(last_ts)
    # surface real, worker-declared NEEDS only — a message whose own `need` field (or a
    # need/blocked-kind body) flags one. We never manufacture: we quote the worker's own
    # field verbatim, and DEDUPE identical needs (with a count) so one recurring floor
    # need reaches Wren as a single honest line, not spam.
    from collections import Counter
    need_counter: Counter = Counter()
    for r in rows[-200:]:
        body = str(r.get("need") or r.get("body") or r.get("message") or "")
        kind = str(r.get("kind") or "")
        declared = r.get("need")
        if declared or "need" in kind.lower() or "blocked" in kind.lower() or \
           body.lower().startswith("need") or "i need" in body.lower():
            snippet = str(declared or body).strip()[:140]
            if snippet:
                need_counter[snippet] += 1
    needs = []
    for snippet, cnt in need_counter.most_common(5):
        needs.append(f"{snippet}" + (f"  (x{cnt} workers)" if cnt > 1 else ""))
    return {"n_msgs": len(rows), "fresh": bool(age is not None and age < FRESH_S),
            "last_ts": last_ts or None, "needs": needs, "source": src}


# ---------------------------------------------------------------------------
# 5. Intercom traffic per floor (real sealed-packet counts)
# ---------------------------------------------------------------------------
def intercom_per_floor() -> dict[int, dict]:
    d = _read_json(INTERCOM_STATE, {})
    pf = d.get("per_floor", {}) if isinstance(d, dict) else {}
    out: dict[int, dict] = {}
    for k, v in pf.items():
        try:
            fl = int(k.split("_")[1])
        except Exception:
            continue
        out[fl] = v
    return out


# ---------------------------------------------------------------------------
# Build one REAL per-floor report (deterministic)
# ---------------------------------------------------------------------------
def build_floor_report(floor: int, chain: dict, hbs: dict, actidx: dict,
                       intercom: dict) -> dict:
    c = chain.get(floor, {})
    hb = hbs.get(floor)
    ai = actidx.get(floor, {})
    wa = worker_activity(floor)
    ic = intercom.get(floor, {})

    lead = c.get("lead_worker_id")
    lead_role = c.get("lead_role")
    n_workers = c.get("n_workers", 0)

    facts: list[str] = []
    needs: list[str] = []
    sources: list[str] = []

    # roster / lead (from chain-of-command)
    if n_workers:
        facts.append(f"{n_workers} workers in chain; lead={lead or 'UNSET'}"
                     f"{(' ('+lead_role+')') if lead_role else ''}")
        sources.append("qsb_worker_chain_of_command.json")
        if not lead:
            needs.append("no FLOOR_OWNER/FLOOR_MANAGER designated as lead in chain-of-command")

    # floor heartbeat (the lead's own honest re-read)
    if hb:
        hb_age = _age_s(hb.get("ts", ""))
        facts.append(hb.get("report", "").strip() or
                     f"roster {hb.get('roster_size')} · mgr {hb.get('floor_manager')}")
        sources.append("qsb_floor_heartbeats.jsonl")
        if hb_age is not None and hb_age > HEARTBEAT_STALE_S:
            needs.append(f"floor heartbeat is stale ({int(hb_age)}s old > {HEARTBEAT_STALE_S}s)")
        if hb.get("per_floor_registries", 0) == 0:
            needs.append("0 per-floor registries — floor has no persistent work output of its own yet")
        if hb.get("gate_execution_allowed") is False and hb.get("execution_mode") == "PREVIEW_ONLY":
            facts.append("gate: PREVIEW_ONLY (execution locked) — expected under audit")
    else:
        needs.append("no floor heartbeat found — lead is not re-reading/reporting its card")

    # activity index (fresh/stale + real source)
    if ai:
        if ai.get("active"):
            facts.append(f"activity index: ACTIVE (age {ai.get('age_s')}s, src {ai.get('signal')})")
        else:
            facts.append(f"activity index: quiet (last {ai.get('last_ts')}, {ai.get('signal')})")
            age = ai.get("age_s")
            if isinstance(age, (int, float)) and age > 7 * 86400:
                needs.append(f"activity index shows NO fresh signal for {int(age/86400)}d")
        sources.append("qsb_floor_activity_index.json")

    # per-worker activity from the activation engine (consumed when present)
    if wa["source"]:
        facts.append(f"{wa['n_msgs']} real worker messages"
                     f"{' (fresh)' if wa['fresh'] else ' (stale)'} via {wa['source']}")
        sources.append(wa["source"])
        for n in wa["needs"]:
            needs.append(f"worker-declared: {n}")
    else:
        facts.append("no per-floor worker-activity file yet (activation engine not flowing to this floor)")

    # intercom sealed-packet traffic
    if ic:
        facts.append(f"intercom: sent {ic.get('sent',0)}, received {ic.get('received',0)}"
                     f" (lift-routed, sealed)")
        sources.append("qsb_floor_intercom_state.json")

    return {
        "floor": floor,
        "lead_worker_id": lead,
        "lead_role": lead_role,
        "n_workers": n_workers,
        "facts": facts,
        "needs": needs,           # ONLY genuine, data-derived needs
        "sources": sorted(set(sources)),
        "generated_ts": utc_iso(),
    }


def report_to_text(rep: dict, lead_summary: str | None = None) -> str:
    fl = rep["floor"]
    head = f"F{fl} chain report — lead {rep.get('lead_worker_id') or 'UNSET'}, {rep['n_workers']} workers"
    lines = [head]
    if lead_summary:
        lines.append(f"  lead: {lead_summary}")
    for f in rep["facts"][:6]:
        lines.append(f"  · {f}")
    if rep["needs"]:
        lines.append("  NEEDS:")
        for n in rep["needs"][:5]:
            lines.append(f"    ! {n}")
    else:
        lines.append("  NEEDS: none surfaced by real data")
    lines.append(f"  [sources: {', '.join(rep['sources'])}]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Optional bounded per-floor LLM lead-summary (respects consult $1/day cap)
# ---------------------------------------------------------------------------
def llm_lead_summary(rep: dict) -> str | None:
    facts = "; ".join(rep["facts"][:5])
    needs = "; ".join(rep["needs"][:4]) or "none"
    prompt = (
        "You are a QSB Tower floor lead reporting UP to Wren. In ONE plain sentence, "
        "faithfully summarise your floor's status. Do NOT invent anything beyond these "
        f"real facts. FACTS: {facts}. NEEDS: {needs}."
    )
    try:
        out = subprocess.run(
            [sys.executable, str(CONSULT_TOOL), "--provider", "deepseek",
             "--prompt", prompt, "--max-tokens", "80"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            return None
        txt = out.stdout.strip()
        try:
            j = json.loads(txt)
            txt = j.get("reply") or j.get("text") or j.get("completion") or txt
        except Exception:
            pass
        return " ".join(txt.split())[:280] or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Delivery — Wren's REAL inbox queue + Codex copy + our audit registry
# ---------------------------------------------------------------------------
def deliver_to_wren(body: str, digest: dict) -> str:
    """Append to Wren's real leadership-comms inbox queue. Her live :8855 client
    drains it via /inbox, prints + acks it, moves it to delivered/wren.jsonl.
    Sender is the honest label 'chain_reporting' (not a CEO, not Wren)."""
    # stable msg_id so re-runs de-dupe against her seen-log
    seed = digest.get("cycle_id", "") + "|wren"
    msg_id = "r_chain_" + hashlib.sha256(seed.encode()).hexdigest()[:14]
    msg = {
        "msg_id": msg_id,
        "kind": "room",                 # room-kind so it shows in her feed like any report
        "from": "chain_reporting",      # honest sender — NOT wren, NOT a CEO
        "to": "wren",
        "ts": utc_iso(),
        "body": body,
    }
    _append_jsonl(WREN_INBOX, msg)
    return msg_id


def deliver_to_codex(body: str, digest: dict) -> str:
    seed = digest.get("cycle_id", "") + "|codex"
    ref = "chain_" + hashlib.sha256(seed.encode()).hexdigest()[:14]
    row = {
        "ts": utc_iso(),
        "tick": "chain_report_copy",
        "ref": ref,
        "source": "qsb_worker_chain_reporting.py",
        "for": "codex",
        "note": "copy of chain-of-command roll-up delivered to Wren",
        "active_floors": digest.get("active_floors"),
        "total_needs": digest.get("total_needs"),
        "body": body,
    }
    _append_jsonl(CODEX_ACT, row)
    return ref


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------
def run_cycle(only_floor: int | None, dry: bool, use_llm: bool, llm_max: int) -> dict:
    chain = load_chain()
    hbs = latest_heartbeats()
    actidx = activity_index()
    intercom = intercom_per_floor()

    floors = sorted(chain.keys())
    if only_floor is not None:
        floors = [only_floor] if only_floor in chain else []

    reports: list[dict] = []
    for fl in floors:
        reports.append(build_floor_report(fl, chain, hbs, actidx, intercom))

    # a floor is "active/reporting" if it has a fresh heartbeat OR fresh worker activity
    def is_active(rep: dict) -> bool:
        ai = actidx.get(rep["floor"], {})
        return bool(ai.get("active")) or any("fresh" in f and "stale" not in f for f in rep["facts"])

    active = [r for r in reports if is_active(r)]
    quiet = [r for r in reports if not is_active(r)]

    # bounded LLM summaries — only for a few active floors, never per worker
    llm_used = 0
    llm_map: dict[int, str] = {}
    if use_llm:
        for r in active[:max(0, llm_max)]:
            s = llm_lead_summary(r)
            if s:
                llm_map[r["floor"]] = s
                llm_used += 1

    total_needs = sum(len(r["needs"]) for r in reports)
    cycle_id = utc_iso() + "|" + hashlib.sha256(
        ",".join(str(r["floor"]) for r in reports).encode()).hexdigest()[:8]

    # Compose the single rolled-up message to Wren (bounded volume: per active floor,
    # + a one-line tail for quiet floors — NOT ~2000 individual worker messages).
    parts: list[str] = []
    parts.append(f"CHAIN-OF-COMMAND ROLL-UP → Wren  ({utc_iso()})")
    parts.append(f"{len(reports)} floors reporting up · {len(active)} active · "
                 f"{len(quiet)} quiet · {total_needs} real NEEDS surfaced")
    parts.append("")
    for r in active:
        parts.append(report_to_text(r, llm_map.get(r["floor"])))
        parts.append("")
    if quiet:
        qids = ", ".join(f"F{r['floor']}" for r in quiet)
        q_needs = sum(len(r["needs"]) for r in quiet)
        parts.append(f"Quiet floors (no fresh signal, honestly idle): {qids}"
                     f"  [{q_needs} standing needs across them]")
    # surface the aggregate needs list explicitly ("telling Wren what they need")
    all_needs = [(r["floor"], n) for r in reports for n in r["needs"]]
    if all_needs:
        parts.append("")
        parts.append("WHAT THE FLOORS NEED (real, data-derived):")
        for fl, n in all_needs[:40]:
            parts.append(f"  F{fl}: {n}")
    body = "\n".join(parts)

    digest = {
        "cycle_id": cycle_id,
        "generated_ts": utc_iso(),
        "floors_reporting": len(reports),
        "active_floors": len(active),
        "quiet_floors": len(quiet),
        "total_needs": total_needs,
        "llm_summaries_used": llm_used,
        "honesty": "R01: every fact + need derived from a cited real source; nothing invented",
    }

    result = {"digest": digest, "reports": reports, "body": body,
              "delivered": {"wren": None, "codex": None}}

    if not dry:
        wren_id = deliver_to_wren(body, digest)
        codex_ref = deliver_to_codex(body, digest)
        result["delivered"] = {"wren_msg_id": wren_id, "codex_ref": codex_ref,
                               "wren_inbox": str(WREN_INBOX.relative_to(ROOT)),
                               "codex_log": str(CODEX_ACT.relative_to(ROOT))}
        # our own append-only audit/rollup registry
        _append_jsonl(CHAIN_REPORTS, {**digest, "delivered": result["delivered"],
                                      "reports": reports})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true", help="run one cycle then exit")
    ap.add_argument("--dry", action="store_true", help="compute + print, do NOT deliver")
    ap.add_argument("--floor", type=int, default=None, help="single floor (proof)")
    ap.add_argument("--llm-summaries", action="store_true",
                    help="add a bounded per-floor LLM lead-summary (respects consult cap)")
    ap.add_argument("--llm-max", type=int, default=6,
                    help="max floors to LLM-summarise per run (default 6)")
    ap.add_argument("--print-body", action="store_true", help="print the report body")
    a = ap.parse_args()

    res = run_cycle(a.floor, a.dry, a.llm_summaries, a.llm_max)
    if a.print_body or a.dry:
        print(res["body"])
        print("\n---")
    print(json.dumps({"digest": res["digest"], "delivered": res["delivered"]},
                     indent=2))


if __name__ == "__main__":
    main()
