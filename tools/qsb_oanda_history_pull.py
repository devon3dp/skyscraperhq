#!/usr/bin/env python3
"""qsb_oanda_history_pull.py — pull the full OANDA practice transaction
history and persist it locally for the PnL aggregator.

Discovered 2026-06-17 (Ross helm): the local F41 lifecycle JSON had only 6
oanda_practice_api closes worth £+9.96, but OANDA's REST shows £+214.26
lifetime across 1648 transactions. Local view was incomplete by orders of
magnitude. This script closes that gap by reading OANDA's authoritative
ledger and writing it to a registry the aggregator can read.

Output:
  data/registries/qsb_oanda_history.jsonl  — one ORDER_FILL per line
  data/registries/qsb_oanda_history_summary.json — totals snapshot

Designed to be re-run on a timer; uses last-saved `lastTransactionID` as
cursor so subsequent runs are incremental.
"""

from __future__ import annotations
import argparse, datetime, json, re, urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.oanda_practice"
OUT_JSONL = ROOT / "data/registries/qsb_oanda_history.jsonl"
OUT_SUMMARY = ROOT / "data/registries/qsb_oanda_history_summary.json"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
CURSOR = ROOT / "data/registries/qsb_oanda_history_cursor.txt"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def read_vault() -> dict:
    env = {}
    for line in VAULT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = re.sub(r"^export\s+", "", line)
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def http_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def pull(env: dict, start_id: int, batch: int = 500) -> tuple[list[dict], int]:
    """Pull transactions from start_id onwards, returning (rows, last_id)."""
    host = env.get("OANDA_API_URL", "https://api-fxpractice.oanda.com").rstrip("/")
    acct = env["OANDA_ACCOUNT_ID"]
    token = env["OANDA_API_TOKEN"]

    # First: find the current lastTransactionID
    summary = http_get(f"{host}/v3/accounts/{acct}/summary", token)
    last_id = int(summary["account"]["lastTransactionID"])

    all_rows: list[dict] = []
    cur = start_id
    while cur <= last_id:
        to = min(cur + batch - 1, last_id)
        url = (f"{host}/v3/accounts/{acct}/transactions/idrange"
               f"?from={cur}&to={to}")
        data = http_get(url, token)
        txns = data.get("transactions", [])
        for t in txns:
            # Keep only ORDER_FILL with non-zero PL (these are the realized
            # close events worth aggregating). Open fills carry pl=0.
            if t.get("type") != "ORDER_FILL":
                continue
            try:
                pl = float(t.get("pl", 0) or 0)
            except Exception:
                pl = 0.0
            if pl == 0:
                continue
            all_rows.append({
                "id": int(t["id"]),
                "ts": t.get("time"),
                "instrument": t.get("instrument"),
                "units": float(t.get("units") or 0),
                "price": float(t.get("price") or 0),
                "pl": pl,
                "balance_after": float(t.get("accountBalance") or 0),
                "reason": t.get("reason"),
            })
        cur = to + 1
    return all_rows, last_id


def summarize(rows: list[dict], last_id: int) -> dict:
    by_inst = defaultdict(lambda: {"pl": 0.0, "trades": 0,
                                     "wins": 0, "losses": 0})
    grand_pl = 0.0
    for r in rows:
        b = by_inst[r["instrument"] or "unknown"]
        pl = r["pl"]
        b["pl"] += pl
        b["trades"] += 1
        if pl > 0:
            b["wins"] += 1
        elif pl < 0:
            b["losses"] += 1
        grand_pl += pl
    return {
        "ts": now_iso(),
        "lastTransactionID": last_id,
        "fills_with_pl": len(rows),
        "grand_pl_gbp": round(grand_pl, 4),
        "by_instrument": {k: {**v, "pl": round(v["pl"], 4)}
                          for k, v in sorted(by_inst.items())},
    }


def stamp_summary(summary: dict, rows_added: int) -> None:
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    with open(F47, "a") as f:
        f.write(json.dumps({
            "ts": now_iso(),
            "kind": "oanda_history_pull",
            "operator": "claude",
            "summary": (
                f"OANDA history: lifetime £{summary['grand_pl_gbp']} "
                f"across {summary['fills_with_pl']} realized fills · "
                f"+{rows_added} new this run · lastID={summary['lastTransactionID']}"
            )[:500],
        }) + "\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true",
                   help="ignore cursor; pull from id=1")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    env = read_vault()
    start = 1
    if not a.full and CURSOR.exists():
        try:
            start = int(CURSOR.read_text().strip() or "1") + 1
        except Exception:
            pass

    rows, last_id = pull(env, start)
    # Append new rows to history jsonl
    if rows and not a.dry_run:
        OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_JSONL, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        CURSOR.write_text(str(last_id))

    # Re-read full history for summary (gives totals across all runs)
    full_rows: list[dict] = []
    if OUT_JSONL.exists():
        for ln in OUT_JSONL.read_text().splitlines():
            if not ln.strip():
                continue
            try:
                full_rows.append(json.loads(ln))
            except Exception:
                continue
    else:
        full_rows = rows

    summary = summarize(full_rows, last_id)

    if a.dry_run:
        print(json.dumps(summary, indent=2)[:3500])
    else:
        stamp_summary(summary, len(rows))
        print(f"[{summary['ts']}] OANDA history: "
              f"lifetime £{summary['grand_pl_gbp']} · "
              f"{summary['fills_with_pl']} fills · "
              f"+{len(rows)} new · lastID={summary['lastTransactionID']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
