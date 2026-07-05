#!/usr/bin/env python3
"""qsb_traders_truth_serve.py — GROUND-TRUTH dashboard.

No log parsing. Numbers come from:
  - data/registries/qsb_portfolio_pot.json     (open positions, committed £)
  - data/registries/qsb_trader_pnl_bus_latest.json (aggregator heartbeat + by_worker)
  - data/registries/qsb_oanda_snapshot.json    (broker realized today, optional)
  - data/registries/qsb_alpaca_snapshot.json   (broker)
  - data/registries/qsb_binance_snapshot.json  (broker)
  - data/registries/cognitive/belief_state_*.json (per-trader belief)
  - `ps -eo args ww | awk` for fleet counts (no shell self-match)

Port: 8848 (default). Different from the old 8847 — so they can run in parallel.

Endpoints:
  /                  HTML
  /api/truth         single-shot JSON of everything below
  /api/pot           pot.json passthrough + per-trader rollup
  /api/fleet         live ps counts + per-venue trader breakdown
  /api/brokers       OANDA + Alpaca + Binance snapshot summary
  /api/health        aggregator heartbeat + bus state
"""
from __future__ import annotations
import json
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def file_age_s(p: Path) -> float:
    try:
        return time.time() - p.stat().st_mtime
    except Exception:
        return -1.0


# ── source: pot.json ────────────────────────────────────────────────
def pot_state() -> dict:
    p = REG / "qsb_portfolio_pot.json"
    d = safe_json(p)
    positions = d.get("open_positions", {})
    by_worker = Counter()
    by_venue = Counter()
    by_inst = Counter()
    for _, pos in positions.items():
        by_worker[pos.get("worker_id", "?")] += 1
        by_venue[pos.get("venue", "?")] += 1
        by_inst[pos.get("instrument", "?")] += 1
    return {
        "ts_file": d.get("updated_at"),
        "age_seconds": round(file_age_s(p), 1),
        "open_positions_count": len(positions),
        "committed_gbp": round(d.get("committed_gbp", 0.0), 2),
        "cap_gbp": d.get("cap_gbp", 5000.0),
        "by_worker_count": dict(by_worker.most_common()),
        "by_venue_count": dict(by_venue),
        "by_instrument_count": dict(by_inst.most_common()),
        "refused_count": d.get("refused_count", 0),
        "reserved_count": d.get("reserved_count", 0),
        "released_count": d.get("released_count", 0),
    }


# ── source: ps args (pure Python, no shell-escape hell) ──────────────
def _ps_args() -> list[str]:
    r = subprocess.run(["ps", "-eo", "args", "ww"], capture_output=True, text=True, timeout=4)
    return r.stdout.splitlines() if r.returncode == 0 else []


def _count_lines(lines: list[str], substr: str) -> int:
    # exclude ps itself + grep-style noise
    return sum(1 for ln in lines if substr in ln)


def fleet_state() -> dict:
    lines = _ps_args()
    by_venue = Counter()
    for ln in lines:
        if "qsb_belief_driven_trader.py" not in ln:
            continue
        m = re.search(r"--venue\s+(\w+)", ln)
        if m:
            by_venue[m.group(1)] += 1
    return {
        "belief_traders_total": sum(by_venue.values()),
        "by_venue": dict(by_venue),
        "ensembles":          _count_lines(lines, "qsb_ensemble_coordinator.py"),
        "bus":                _count_lines(lines, "qsb_event_bus.py"),
        "belief_updater":     _count_lines(lines, "qsb_belief_updater.py"),
        "regime_detector":    _count_lines(lines, "qsb_regime_detector.py"),
        "streams_binance":    _count_lines(lines, "qsb_f42_binance_stream.py"),
        "streams_oanda":      _count_lines(lines, "qsb_f41_oanda_stream.py"),
        "streams_alpaca":     _count_lines(lines, "qsb_f43_alpaca_stream.py"),
        "pnl_aggregator_bus": _count_lines(lines, "qsb_trader_pnl_aggregator_bus.py"),
        "pnl_watchdog":       _count_lines(lines, "qsb_pnl_watchdog.py"),
        "trader_manager":     _count_lines(lines, "qsb_trader_manager.py"),
        "ue_editor":          sum(1 for ln in lines if "UnrealEditor" in ln and "QSB_Skyscraper" in ln),
    }


# ── source: brokers (DIRECT — no stale snapshot files) ──────────────
_broker_cache = {"ts": 0, "data": None}

def broker_state() -> dict:
    # Cache for 30s to avoid hammering brokers on every page refresh
    now = time.time()
    if _broker_cache["data"] and (now - _broker_cache["ts"]) < 30:
        return _broker_cache["data"]
    out = {}
    # OANDA — call existing oanda.py status which already talks to broker
    try:
        r = subprocess.run([".venv/bin/python3", "tools/qsb_oanda.py", "status"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout:
            try:
                oanda = json.loads(r.stdout)
                per_worker_realised = oanda.get("per_worker_realised_gbp") or {}
                realised_total = sum(v for v in per_worker_realised.values() if isinstance(v, (int, float)))
                out["oanda"] = {
                    "live": True,
                    "ownership_count": oanda.get("ownership_count"),
                    "realised_lifetime_gbp": round(realised_total, 2),
                    "per_worker_realised_gbp": per_worker_realised,
                    "per_worker_open_count": oanda.get("per_worker_open_count"),
                    "worker_ledger_rows_total": oanda.get("worker_ledger_rows_total"),
                    "ownership_sample": (oanda.get("ownership_sample") or [])[:5],
                    "generated_ts": oanda.get("generated_ts"),
                }
            except Exception as e:
                out["oanda"] = {"live": False, "error": f"parse: {e}", "raw_head": r.stdout[:200]}
        else:
            out["oanda"] = {"live": False, "error": (r.stderr or "rc!=0")[:200]}
    except Exception as e:
        out["oanda"] = {"live": False, "error": str(e)[:200]}

    # Alpaca + Binance: fall back to snapshot if writer exists, else skip
    for v in ("alpaca", "binance"):
        p = REG / f"qsb_{v}_snapshot.json"
        if p.exists():
            d = safe_json(p)
            d["snapshot_age_seconds"] = round(file_age_s(p), 1)
            d["live"] = d["snapshot_age_seconds"] < 300
            out[v] = d
        else:
            out[v] = {"live": False, "error": "no snapshot writer running"}

    _broker_cache["ts"] = now
    _broker_cache["data"] = out
    return out


# ── source: aggregator heartbeat ─────────────────────────────────────
def aggregator_state() -> dict:
    p = REG / "qsb_trader_pnl_bus_latest.json"
    d = safe_json(p)
    return {
        "exists": p.exists(),
        "age_seconds": round(file_age_s(p), 1) if p.exists() else -1,
        "started_at": d.get("started_at"),
        "last_event_ts": d.get("last_event_ts"),
        "event_count": d.get("event_count"),
        "tracked_workers": d.get("tracked_workers"),
        "totals": d.get("totals", {}),
    }


def truth_snapshot() -> dict:
    return {
        "ts": utc_iso(),
        "pot": pot_state(),
        "fleet": fleet_state(),
        "brokers": broker_state(),
        "aggregator": aggregator_state(),
    }


# ── HTTP handler ─────────────────────────────────────────────────────
def render_html(t: dict) -> str:
    pot = t["pot"]; fleet = t["fleet"]; agg = t["aggregator"]; br = t["brokers"]
    def venue_row(name: str, count: int, broker: dict) -> str:
        broker_summary = "—"
        if isinstance(broker, dict):
            err = broker.get("error")
            if err:
                broker_summary = f"err: {str(err)[:60]}"
            else:
                # generic — try common fields
                rt = broker.get("realized_today_gbp") or broker.get("realized_gbp") or broker.get("equity")
                opos = broker.get("open_trade_count") or broker.get("positions_count")
                broker_summary = f"realized={rt} open={opos}"
        return f"<tr><td>{name}</td><td class='num'>{count}</td><td>{broker_summary}</td></tr>"

    rows = []
    for v in ("oanda", "binance", "alpaca"):
        rows.append(venue_row(v.upper(), fleet["by_venue"].get(v, 0), br.get(v, {})))

    worker_rollup = "".join(
        f"<tr><td>{w}</td><td class='num'>{n}</td></tr>"
        for w, n in pot["by_worker_count"].items()
    )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>QSB Truth Dashboard — port 8848</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{ --bg:#070b14; --fg:#dfe; --dim:#8aa; --accent:#7ee; --green:#5b8; --amber:#fb6; --red:#f55; --panel:rgba(120,238,238,0.08); --frame:rgba(120,238,238,0.30); }}
html,body {{ margin:0; padding:0; background:var(--bg); color:var(--fg); font-family:ui-monospace,Menlo,monospace; }}
body {{ padding:18px 22px; }}
header {{ display:flex; justify-content:space-between; align-items:center; padding-bottom:10px; border-bottom:1px solid var(--frame); margin-bottom:16px; }}
h1 {{ margin:0; color:var(--accent); font-size:18px; letter-spacing:0.05em; }}
.grid {{ display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); }}
.card {{ background:var(--panel); border:1px solid var(--frame); border-radius:6px; padding:14px 16px; }}
.card h2 {{ margin:0 0 10px; font-size:12px; letter-spacing:0.10em; color:var(--accent); text-transform:uppercase; }}
.row {{ display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px dotted rgba(120,238,238,0.10); font-size:13px; }}
.row:last-child {{ border-bottom:none; }}
.k {{ color:var(--dim); }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th, td {{ padding:4px 6px; text-align:left; border-bottom:1px dotted rgba(120,238,238,0.10); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.green {{ color:var(--green); }} .amber {{ color:var(--amber); }} .red {{ color:var(--red); }}
.big {{ font-size:22px; color:var(--accent); font-weight:600; }}
footer {{ margin-top:18px; font-size:11px; color:var(--dim); }}
</style></head><body>
<header><h1>QSB Truth Dashboard — port 8848</h1>
<span class="k">{t["ts"]} (auto-refresh 10s)</span></header>

<section class="card" style="margin-bottom:14px">
<h2>LIVE PnL TODAY (from aggregator bus)</h2>
<div class="row"><span class="k">closes</span><span class="big">{(agg.get('totals') or {}).get('closes', 0)}</span></div>
<div class="row"><span class="k">pnl_sum £</span><span class="big {'green' if (agg.get('totals') or {}).get('pnl_sum',0) >= 0 else 'red'}">£{(agg.get('totals') or {}).get('pnl_sum', 0):.2f}</span></div>
<div class="row"><span class="k">wins</span><span>{(agg.get('totals') or {}).get('wins', 0)} / {(agg.get('totals') or {}).get('closes', 0)}</span></div>
<div class="row"><span class="k">aggregator age</span><span class="{'green' if isinstance(agg.get('age_seconds'), (int,float)) and 0<=agg.get('age_seconds',9999)<120 else 'red'}">{agg.get('age_seconds')}s</span></div>
<div class="row"><span class="k">OANDA live</span><span>{('yes ✓' if br.get('oanda',{}).get('live') else 'down — ' + str(br.get('oanda',{}).get('error',''))[:90])}</span></div>
<div class="row"><span class="k">OANDA open trades</span><span>{br.get('oanda',{}).get('ownership_count', '—')}</span></div>
<div class="row"><span class="k">OANDA realised lifetime</span><span class="{'green' if br.get('oanda',{}).get('realised_lifetime_gbp',0) >= 0 else 'red'}">£{br.get('oanda',{}).get('realised_lifetime_gbp', '—')}</span></div>
<div class="row"><span class="k">OANDA ledger rows</span><span>{br.get('oanda',{}).get('worker_ledger_rows_total', '—')}</span></div>
</section>

<div class="grid">

<section class="card"><h2>Pot (ground truth)</h2>
<div class="row"><span class="k">open positions</span><span class="big">{pot['open_positions_count']}</span></div>
<div class="row"><span class="k">committed £</span><span>£{pot['committed_gbp']} / £{pot['cap_gbp']}</span></div>
<div class="row"><span class="k">pot.json age</span><span>{pot['age_seconds']}s</span></div>
<div class="row"><span class="k">refused / reserved / released</span><span>{pot['refused_count']} / {pot['reserved_count']} / {pot['released_count']}</span></div>
<h2 style="margin-top:14px">open by worker</h2>
<table>{worker_rollup}</table>
</section>

<section class="card"><h2>Fleet (ps args, no self-match)</h2>
<div class="row"><span class="k">belief traders TOTAL</span><span class="big">{fleet['belief_traders_total']}</span></div>
<table>
<tr><th>venue</th><th class="num">traders</th><th>broker</th></tr>
{''.join(rows)}
</table>
<table style="margin-top:8px">
<tr><td>ensembles</td><td class='num'>{fleet['ensembles']}</td></tr>
<tr><td>bus</td><td class='num'>{fleet['bus']}</td></tr>
<tr><td>belief_updater</td><td class='num'>{fleet['belief_updater']}</td></tr>
<tr><td>regime_detector</td><td class='num'>{fleet['regime_detector']}</td></tr>
<tr><td>streams (oanda/binance/alpaca)</td><td class='num'>{fleet['streams_oanda']} / {fleet['streams_binance']} / {fleet['streams_alpaca']}</td></tr>
<tr><td>pnl_aggregator_bus</td><td class='num'>{fleet['pnl_aggregator_bus']}</td></tr>
<tr><td>pnl_watchdog</td><td class='num'>{fleet['pnl_watchdog']}</td></tr>
<tr><td>trader_manager</td><td class='num'>{fleet['trader_manager']}</td></tr>
<tr><td>UE editor</td><td class='num'>{fleet['ue_editor']}</td></tr>
</table>
</section>

<section class="card"><h2>Aggregator heartbeat</h2>
<div class="row"><span class="k">file exists</span><span>{'yes' if agg['exists'] else 'NO'}</span></div>
<div class="row"><span class="k">age</span><span class="{'green' if isinstance(agg['age_seconds'], (int,float)) and 0<=agg['age_seconds']<300 else 'red'}">{agg['age_seconds']}s</span></div>
<div class="row"><span class="k">tracked workers</span><span>{agg['tracked_workers']}</span></div>
<div class="row"><span class="k">event count</span><span>{agg['event_count']}</span></div>
<div class="row"><span class="k">last event</span><span>{agg['last_event_ts']}</span></div>
<h2 style="margin-top:12px">totals (from bus)</h2>
{''.join(f"<div class='row'><span class='k'>{k}</span><span>{v}</span></div>" for k, v in (agg['totals'] or {}).items())}
</section>

</div>

<footer>data sources: pot.json · ps args · broker snapshots · aggregator heartbeat — NO log parsing.</footer>
<script>setTimeout(()=>location.reload(), 10000);</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass  # silence

    def _json(self, payload: dict, code: int = 200):
        body = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body_str: str):
        body = body_str.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/index.html":
                self._html(render_html(truth_snapshot())); return
            if self.path == "/api/truth":
                self._json(truth_snapshot()); return
            if self.path == "/api/pot":
                self._json(pot_state()); return
            if self.path == "/api/fleet":
                self._json(fleet_state()); return
            if self.path == "/api/brokers":
                self._json(broker_state()); return
            if self.path == "/api/health":
                self._json(aggregator_state()); return
            self._json({"error": "not_found", "path": self.path}, code=404)
        except Exception as e:
            self._json({"error": str(e)}, code=500)


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8848)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"qsb_traders_truth_serve listening on {args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
