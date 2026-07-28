#!/usr/bin/env python3
"""
qsb_agentic_traders_dash.py — LIVE dashboard for the agentic (belief-driven) trading fleet.
2026-07-20, Ross: "how are the agentic traders doing and we need a dash ? u can make first dash".

REAL DATA ONLY — every number is computed server-side from the live registries:
  - fleet size            : ps count of tools/qsb_belief_driven_trader.py
  - capital pot / venues  : data/registries/qsb_portfolio_pot.json
  - open positions        : same pot (open_positions dict) — count, by venue, by currency, top notionals
  - today order flow      : tail of data/registries/qsb_broker_place_audit.jsonl (placed vs blocked + reasons)
  - realized PnL          : data/registries/qsb_trader_pnl_bus_latest.json
  - event bus             : state/qsb_bus.sock bound?
It is READ-ONLY: it never places orders, never flips a gate, never writes project files.
Additive service on :8863 (does not touch any existing dashboard).
Run:  python3 tools/qsb_agentic_traders_dash.py --port 8863
"""
import json, os, re, sys, glob, subprocess, argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
POT = REG / "qsb_portfolio_pot.json"
AUDIT = REG / "qsb_broker_place_audit.jsonl"
PNL = REG / "qsb_trader_pnl_bus_latest.json"
BUS_SOCK = ROOT / "state" / "qsb_bus.sock"
COG = REG / "cognitive"                         # belief_state_*.json (live trader brains)
HIST_SUMMARY = REG / "qsb_oanda_history_summary.json"  # broker truth per instrument
PNL_TAIL = REG / "qsb_trader_pnl_bus_tail.jsonl"       # individual close events (scalp tape)
RECON_AUDIT = REG / "qsb_pot_broker_reconcile_audit.jsonl"  # self-healing reconcile log

# 2026-07-27 teaching panel: run the fleet's OWN gate on the live belief brains.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from belief_updater_math import confidence_to_act
except Exception:
    confidence_to_act = None

# index/metal CFD class — the negative-expectancy bleeders the teaching gated OFF
IDX_CLASS = {"JP225_USD", "NAS100_USD", "US30_USD", "SPX500_USD", "DE30_EUR", "XAU_USD", "XAG_USD"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=6).stdout.strip()
    except Exception:
        return ""


def _tail_lines(path: Path, max_bytes=12_000_000):
    """Read the last max_bytes of a (possibly huge) file, return complete lines."""
    try:
        sz = path.stat().st_size
        with open(path, "rb") as f:
            if sz > max_bytes:
                f.seek(sz - max_bytes)
                f.readline()  # discard partial first line
            data = f.read()
        return data.decode("utf-8", "replace").splitlines()
    except Exception:
        return []


def _fleet_alive():
    n = _sh("ps -eo cmd ww 2>/dev/null | grep -c '[b]elief_driven_trader.py'")
    return int(n) if n.isdigit() else 0


CCY_RE = re.compile(r"([A-Z]{3})")


def _ccy_of(instrument, venue):
    # crude but real: GBP_USD -> GBP exposure bucket; crypto USDT -> USD; equities -> USD
    if not instrument:
        return "?"
    if "_" in instrument:
        return instrument.split("_")[0]
    if instrument.endswith("USDT") or instrument.endswith("USDC"):
        return "USD"
    return "USD"


def _teaching():
    """Prove the teaching LIVE: broker P/L per instrument alongside each taught
    belief brain's real gate decision (confidence_to_act on the live file)."""
    broker = {}
    try:
        hs = json.loads(HIST_SUMMARY.read_text())
        for ins, s in (hs.get("by_instrument") or {}).items():
            n = s.get("trades", 0) or 0
            broker[ins] = {"pl": round(s.get("pl", 0), 2), "trades": n,
                           "exp": round(s.get("pl", 0) / n, 3) if n else 0}
    except Exception:
        pass
    seen = {}
    if confidence_to_act:
        for path in glob.glob(str(COG / "belief_state_*.json")):
            base = os.path.basename(path)[len("belief_state_"):-len(".json")]
            if "__" not in base:
                continue
            _worker, instrument = base.split("__", 1)
            if instrument in seen or instrument not in broker:
                continue  # one row per instrument; only those with broker truth
            try:
                b = json.loads(Path(path).read_text())
            except Exception:
                continue
            sf = b.get("strategy_fitness", {})
            if not all(k in sf for k in ("win_rate", "expectancy", "n_trades")) or "regime" not in b:
                continue
            act, why = confidence_to_act(b)
            seen[instrument] = {
                "instrument": instrument, "act": bool(act), "why": why,
                "win_rate": round(sf["win_rate"], 3), "expectancy": round(sf["expectancy"], 3),
                "n": sf["n_trades"], "broker_pl": broker[instrument]["pl"],
                "broker_exp": broker[instrument]["exp"], "broker_trades": broker[instrument]["trades"],
            }
    rows = sorted(seen.values(), key=lambda r: r["broker_pl"])
    total_pl = round(sum(v["pl"] for v in broker.values()), 2)
    idx_pl = round(sum(broker.get(i, {}).get("pl", 0) for i in IDX_CLASS), 2)
    return {
        "rows": rows,
        "trade_n": sum(1 for r in rows if r["act"]),
        "refuse_n": sum(1 for r in rows if not r["act"]),
        "total_pl": total_pl, "idx_class_pl": idx_pl,
        "book_if_cut": round(total_pl - idx_pl, 2),
    }


def _hours_view():
    """Winning-hours size multipliers for the two proven engines (from the live
    HOUR_SIZE_MULT table), plus the current UTC hour so the dash can highlight it."""
    cur = datetime.now(timezone.utc).hour
    try:
        from belief_updater_math import HOUR_SIZE_MULT
    except Exception:
        HOUR_SIZE_MULT = {}
    rows = []
    for ins in ("EUR_USD", "USD_JPY"):
        rows.append({"instrument": ins,
                     "mults": [HOUR_SIZE_MULT.get(ins, {}).get(h, 1.0) for h in range(24)]})
    return {"cur_hour": cur, "rows": rows}


def _pot_health():
    """Self-healing pot panel — proves the orphan-clog fix (release-on-close +
    reconcile timer). All from live files, no slow broker call."""
    out = {"released_count": None, "committed": 0, "cap": 0, "pct": 0,
           "recon": None}
    try:
        pot = json.loads(POT.read_text())
        out["released_count"] = pot.get("released_count")
        out["committed"] = round(pot.get("committed_gbp", 0), 0)
        out["cap"] = round(pot.get("cap_gbp", 0), 0)
        out["pct"] = round(100 * out["committed"] / out["cap"], 0) if out["cap"] else 0
    except Exception:
        pass
    try:
        last = _tail_lines(RECON_AUDIT)[-1]
        r = json.loads(last)
        ts = r.get("ts", "")
        ago = None
        try:
            t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            ago = int((datetime.now(timezone.utc) - t).total_seconds())
        except Exception:
            pass
        out["recon"] = {"ts": ts[:19], "ago_s": ago, "removed": r.get("removed"),
                        "freed_gbp": r.get("freed_gbp")}
    except Exception:
        pass
    return out


def _scalp_tape():
    """Recent CLOSES from OANDA broker truth (qsb_oanda_history.jsonl) — includes
    broker-side take-profit/stop closes that the pnl bus misses. A fill with a
    non-null 'pl' is a realized close."""
    hist = REG / "qsb_oanda_history.jsonl"
    lines = _tail_lines(hist, max_bytes=2_000_000)
    today = _today()
    closes = []
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        pl = d.get("pl", d.get("realizedPL"))
        if pl in (None, ""):
            continue
        ts = d.get("ts", d.get("time", ""))
        try:
            pl = float(pl)
        except Exception:
            continue
        closes.append({"ts": ts, "instrument": d.get("instrument"), "pnl": round(pl, 3),
                       "won": pl > 0, "reason": (d.get("reason", "") or "").replace("_ORDER", "")[:16]})
    today_rows = [c for c in closes if (c["ts"] or "").startswith(today)]
    wins_today = sum(1 for c in today_rows if c["won"])
    pnl_today = round(sum(c["pnl"] for c in today_rows), 3)
    tape = [{**c, "ts": (c["ts"] or "")[11:19]} for c in closes[-14:]]
    return {"tape": list(reversed(tape)),
            "closes_today": len(today_rows), "wins_today": wins_today,
            "wr_today": round(100 * wins_today / len(today_rows), 0) if today_rows else 0,
            "pnl_today": pnl_today}


def _equity_curve(n=80):
    """Account equity curve from broker fills (balance_after). Real money curve."""
    hist = REG / "qsb_oanda_history.jsonl"
    lines = _tail_lines(hist, max_bytes=1_000_000)
    pts = []
    for ln in lines:
        try:
            d = json.loads(ln)
            ba = d.get("balance_after")
            if ba is not None:
                pts.append(round(float(ba), 3))
        except Exception:
            pass
    pts = pts[-n:]
    if not pts:
        return {"pts": [], "first": 0, "last": 0, "min": 0, "max": 0, "delta": 0}
    return {"pts": pts, "first": pts[0], "last": pts[-1],
            "min": min(pts), "max": max(pts), "delta": round(pts[-1] - pts[0], 2)}


def build_data():
    d = {"ts": _now(), "today": _today()}
    d["teaching"] = _teaching()
    d["hours"] = _hours_view()
    d["pot_health"] = _pot_health()
    d["scalp"] = _scalp_tape()
    d["equity"] = _equity_curve()
    try:
        d["live"] = json.loads((REG / "qsb_oanda_live.json").read_text())
    except Exception:
        d["live"] = {"ok": False}
    d["fleet_alive"] = _fleet_alive()
    d["bus_bound"] = bool(_sh(f"ss -xlnp 2>/dev/null | grep -c qsb_bus") not in ("", "0"))

    # ---- capital pot + open positions ----
    pot = {}
    try:
        pot = json.loads(POT.read_text())
    except Exception:
        pot = {}
    cap = pot.get("cap_gbp", 0) or 0
    committed = pot.get("committed_gbp", 0) or 0
    d["pot"] = {
        "cap_gbp": round(cap, 2), "committed_gbp": round(committed, 2),
        "pct": round(100 * committed / cap, 1) if cap else 0,
        "by_venue": {k: round(v, 2) for k, v in (pot.get("by_venue") or {}).items()},
        "refused": pot.get("refused_count"), "reserved": pot.get("reserved_count"),
        "released": pot.get("released_count"), "updated_at": pot.get("updated_at"),
    }
    positions = pot.get("open_positions") or {}
    by_venue_cnt, by_ccy_notional, top = {}, {}, []
    for pid, p in positions.items():
        v = p.get("venue", "?"); by_venue_cnt[v] = by_venue_cnt.get(v, 0) + 1
        ccy = _ccy_of(p.get("instrument"), v)
        ng = p.get("notional_gbp", 0) or 0
        by_ccy_notional[ccy] = round(by_ccy_notional.get(ccy, 0) + ng, 2)
        top.append({"worker": p.get("worker_id"), "instrument": p.get("instrument"),
                    "venue": v, "notional_gbp": round(ng, 2), "opened": (p.get("opened_ts") or "")[:16]})
    top.sort(key=lambda x: x["notional_gbp"], reverse=True)
    d["positions"] = {"count": len(positions), "by_venue": by_venue_cnt,
                      "by_ccy_notional": dict(sorted(by_ccy_notional.items(), key=lambda x: -x[1])),
                      "top": top[:10]}

    # ---- today's order flow from audit tail ----
    lines = _tail_lines(AUDIT)
    today = d["today"]
    placed = blocked = 0
    reasons, workers, recent = {}, {}, []
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        ts = r.get("ts", "")
        if ts.startswith(today):
            w = r.get("worker_id", "?"); workers[w] = workers.get(w, 0) + 1
            if r.get("ok"):
                placed += 1
            else:
                blocked += 1
                rs = (r.get("reason", "") or "").split("(")[0].strip()[:26] or "?"
                reasons[rs] = reasons.get(rs, 0) + 1
    for ln in lines[-14:]:
        try:
            r = json.loads(ln)
            recent.append({"ts": (r.get("ts", "") or "")[:19], "worker": r.get("worker_id"),
                           "venue": r.get("venue"), "side": r.get("side"),
                           "ok": r.get("ok"), "reason": (r.get("reason", "") or "")[:40]})
        except Exception:
            pass
    d["flow"] = {"placed": placed, "blocked": blocked,
                 "reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])[:6]),
                 "workers": dict(sorted(workers.items(), key=lambda x: -x[1])[:8]),
                 "recent": list(reversed(recent))}

    # ---- realized PnL ----
    try:
        pnl = json.loads(PNL.read_text())
        t = pnl.get("totals", {})
        d["pnl"] = {"closes": t.get("closes", 0), "wins": t.get("wins", 0),
                    "pnl_sum": round(t.get("pnl_sum", 0), 4), "as_of": (pnl.get("ts") or "")[:19],
                    "by_worker": {k: {"wins": v.get("wins"), "losses": v.get("losses"),
                                      "pnl": round(v.get("pnl_sum", 0), 3)}
                                  for k, v in (pnl.get("by_worker") or {}).items()}}
    except Exception:
        d["pnl"] = {"closes": 0, "wins": 0, "pnl_sum": 0, "as_of": "n/a", "by_worker": {}}

    # ---- gauges (arc gauges): capital deployed, per-currency cap utilization, win rate, fleet ----
    CCY_CAPS = {"GBP": 2500, "EUR": 2500, "USD": 4500, "USDT": 1500}
    ccyN = d["positions"]["by_ccy_notional"]
    gauges = []
    gauges.append({"label": "Capital deployed", "val": d["pot"]["committed_gbp"],
                   "max": d["pot"]["cap_gbp"], "pct": d["pot"]["pct"], "unit": "£"})
    for c, cap in CCY_CAPS.items():
        used = round(ccyN.get(c, 0), 2)
        gauges.append({"label": f"{c} cap", "val": used, "max": cap,
                       "pct": round(100 * used / cap, 1) if cap else 0, "unit": "£"})
    cl = d["pnl"]["closes"] or 0
    wr = round(100 * d["pnl"]["wins"] / cl, 1) if cl else 0
    gauges.append({"label": "Win rate", "val": wr, "max": 100, "pct": wr, "unit": "%"})
    fh = round(100 * d["fleet_alive"] / 45, 0) if d["fleet_alive"] else 0
    gauges.append({"label": "Fleet alive", "val": d["fleet_alive"], "max": 45,
                   "pct": min(100, fh), "unit": ""})
    # teaching-derived gauges: how disciplined is the fleet right now
    tch = d.get("teaching", {})
    tn, rn = tch.get("trade_n", 0), tch.get("refuse_n", 0)
    tot = tn + rn
    gauges.append({"label": "Losers gated", "val": rn, "max": tot or 1,
                   "pct": round(100 * rn / tot, 0) if tot else 0, "unit": ""})
    gauges.append({"label": "+EV engines live", "val": tn, "max": tot or 1,
                   "pct": round(100 * tn / tot, 0) if tot else 0, "unit": ""})
    d["gauges"] = gauges
    # hero progress bars (horizontal, animated) — the day's win story at a glance
    total_pl = tch.get("total_pl", 0) or 0
    cut = tch.get("book_if_cut", 0) or 0
    LO, HI = -2000.0, 500.0  # book recovery scale
    d["hero"] = [
        {"label": "Fleet discipline (losers gated)",
         "pct": round(100 * rn / tot, 0) if tot else 0,
         "text": f"{rn} of {tot} instruments gated OFF", "col": "grn"},
        {"label": "Realized book (broker truth)",
         "pct": round(100 * (total_pl - LO) / (HI - LO), 1),
         "text": f"£{total_pl:,.2f}", "col": "red" if total_pl < 0 else "grn"},
        {"label": "Book if index/metal class cut",
         "pct": round(100 * (cut - LO) / (HI - LO), 1),
         "text": f"£{cut:,.2f}", "col": "grn" if cut >= 0 else "red"},
        {"label": "USD budget in use",
         "pct": round(100 * (d["positions"]["by_ccy_notional"].get("USD", 0)) / 4500, 1),
         "text": f"£{d['positions']['by_ccy_notional'].get('USD', 0):,.0f} / £4,500", "col": "gold"},
    ]
    return d


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Agentic Traders — Live</title>
<style>
:root{--bg:#0a0e17;--pane:#121a2b;--pane2:#0f1626;--ink:#e8eefc;--dim:#8aa0c8;--line:#233;
--grn:#22c55e;--red:#ef4444;--gold:#eab308;--blu:#3b82f6;--cy:#22d3ee}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:0 0 2px}.sub{color:var(--dim);font-size:13px;margin-bottom:14px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}
.gaugerow{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:14px}
.gauge{background:var(--pane);border:1px solid #22304e;border-radius:12px;padding:10px 6px 6px;text-align:center}
.gauge svg{display:block;margin:0 auto}
.gauge .gv{font-size:18px;font-weight:700;margin-top:-38px}
.gauge .gl{font-size:11.5px;color:var(--dim);margin-top:20px}
.gauge .gm{font-size:10px;color:var(--dim)}
.card{background:var(--pane);border:1px solid #22304e;border-radius:12px;padding:14px}
.card h2{margin:0 0 10px;font-size:13px;letter-spacing:.5px;color:var(--gold);text-transform:uppercase}
.big{font-size:30px;font-weight:700}.mut{color:var(--dim);font-size:12px}
.row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #1b2740}
.row:last-child{border:0}.pos{color:var(--grn)}.neg{color:var(--red)}
.bar{height:8px;background:#1b2740;border-radius:6px;overflow:hidden;margin-top:6px}
.bar>span{display:block;height:100%;transition:width .8s cubic-bezier(.25,1,.35,1)}
.hbar{height:16px;background:#141d30;border-radius:9px;overflow:hidden;margin-top:5px;position:relative}
.hbar>span{display:block;height:100%;border-radius:9px;transition:width 1s cubic-bezier(.25,1,.35,1);
  background-image:linear-gradient(90deg,rgba(255,255,255,.12),rgba(255,255,255,0))}
.wbar{height:5px;background:#1b2740;border-radius:4px;overflow:hidden;margin-top:3px}
.wbar>span{display:block;height:100%;transition:width .8s cubic-bezier(.25,1,.35,1)}
.mbar{height:5px;background:#141d30;border-radius:4px;overflow:hidden;margin-top:3px}
.mbar>span{display:block;height:100%;transition:width .8s cubic-bezier(.25,1,.35,1)}
.pill{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;border:1px solid #2a3a5c}
.ok{color:var(--grn)}.bad{color:var(--red);opacity:.85}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td,th{text-align:left;padding:4px 6px;border-bottom:1px solid #1b2740}th{color:var(--dim);font-weight:600}
.mono{font-family:ui-monospace,Menlo,monospace}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
</style></head><body><div class=wrap>
<h1>🤖 Agentic Traders — Live</h1>
<div class=sub id=sub>loading…</div>
<div class=card style="margin-bottom:14px;border-color:#2c3f66" id=livecard></div>
<div class=gaugerow id=gauges></div>
<div class=card style="margin-bottom:14px" id=herocard>
<h2>📊 Live progress</h2><div id=hero></div></div>
<div class=card style="margin-bottom:14px" id=teachcard>
<h2>🎓 Teaching — belief brains vs broker truth</h2>
<div id=teachsum class=sub style="margin-bottom:8px">loading…</div>
<table id=teach><thead><tr><th>instrument</th><th>broker P/L</th><th>£/trade</th><th>taught win_rate</th><th>expectancy</th><th>live gate</th></tr></thead><tbody></tbody></table>
</div>
<div class=card style="margin-bottom:14px" id=hourscard>
<h2>🕐 Winning hours — size multiplier by UTC hour (proven engines)</h2>
<div id=hours></div>
<div class=mut style="margin-top:6px">green = size UP in the edge hours · red = shrink in the bleed hours · outlined = current UTC hour</div>
</div>
<div class=card style="margin-bottom:14px" id=eqcard>
<h2>📈 Account equity — live curve</h2><div id=equity></div></div>
<div class=grid style="margin-bottom:14px" id=scalprow></div>
<div class=card style="margin-bottom:14px" id=tapecard>
<h2>⚡ Scalp tape — recent closes</h2>
<table id=tape><thead><tr><th>time (UTC)</th><th>instrument</th><th>P/L</th><th>exit reason</th></tr></thead><tbody></tbody></table>
</div>
<div class=grid id=top></div>
<div class=grid style="margin-top:12px" id=mid></div>
<div class=card style="margin-top:12px"><h2>Recent order attempts (live)</h2>
<table id=recent><thead><tr><th>time</th><th>worker</th><th>venue</th><th>side</th><th>result</th></tr></thead><tbody></tbody></table></div>
<div class=sub style="margin-top:10px">READ-ONLY · paper/practice/testnet only · real-money gates LOCKED · auto-refresh 5s</div>
</div>
<script>
const $=id=>document.getElementById(id);
const money=n=>'£'+(n||0).toLocaleString(undefined,{maximumFractionDigits:2});
function bar(pct,col){return `<div class=bar><span style="width:${Math.min(100,pct)}%;background:${col}"></span></div>`}
function kv(o){return Object.entries(o||{}).map(([k,v])=>`<div class=row><span class=mut>${k}</span><b>${v}</b></div>`).join('')||'<div class=mut>none</div>'}
function gaugeSVG(g){
 const pct=Math.max(0,Math.min(100,g.pct||0)),r=32,c=2*Math.PI*r,off=c*(1-pct/100);
 const col=pct>=90?'var(--red)':pct>=70?'var(--gold)':'var(--grn)';
 const val=g.unit==='£'?money(g.val):(Math.round(g.val*10)/10+(g.unit||''));
 const mx=g.unit==='£'?money(g.max):(g.max+(g.unit||''));
 return `<div class=gauge><svg width=88 height=78 viewBox="0 0 90 82">
   <circle cx=45 cy=41 r=${r} fill=none stroke="#1b2740" stroke-width=8/>
   <circle cx=45 cy=41 r=${r} fill=none stroke="${col}" stroke-width=8 stroke-linecap=round
     stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 45 41)"
     style="transition:stroke-dashoffset .8s"/></svg>
   <div class=gv style="color:${col}">${Math.round(pct)}%</div>
   <div class=gl>${g.label}</div><div class=gm>${val} / ${mx}</div></div>`;
}
async function tick(){
 let d; try{d=await (await fetch('/api/data')).json()}catch(e){$('sub').textContent='fetch error';return}
 const busCol=d.bus_bound?'var(--grn)':'var(--red)';
 $('sub').innerHTML=`as of ${d.ts} · <span class=pill><span class=dot style="background:${busCol}"></span>event bus ${d.bus_bound?'LIVE':'DOWN'}</span>`;
 const lv=d.live||{ok:false};
 if(lv.ok){
   const up=(lv.NAV||0)>=(lv.balance||0);
   const big=(lbl,val,cls)=>`<div style="flex:1;min-width:120px"><div class=mut style="font-size:11px">${lbl}</div><div class="big ${cls||''}" style="font-size:26px">${val}</div></div>`;
   $('livecard').innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
       <h2 style="margin:0">🟢 LIVE — OANDA practice account</h2><span class=mut>snapshot ${lv.ts||''}</span></div>
     <div style="display:flex;gap:16px;flex-wrap:wrap">
       ${big('NAV (equity)', money(lv.NAV), up?'pos':'neg')}
       ${big('Balance (realized)', money(lv.balance))}
       ${big('Unrealized P/L', (lv.unrealized_pl>=0?'+':'')+money(lv.unrealized_pl), lv.unrealized_pl>=0?'pos':'neg')}
       ${big('Realized today', (lv.realized_pl_today>=0?'+':'')+money(lv.realized_pl_today), lv.realized_pl_today>=0?'pos':'neg')}
       ${big('Open trades', lv.open_trades!=null?lv.open_trades:'—')}
     </div>`;
 } else { $('livecard').innerHTML='<h2>🟢 LIVE</h2><div class=mut>live snapshot warming up (30s timer)…</div>'; }
 $('gauges').innerHTML=(d.gauges||[]).map(gaugeSVG).join('');
 $('hero').innerHTML=(d.hero||[]).map(h=>`
   <div style="margin-bottom:11px">
     <div class=row style="border:0;padding:0"><span class=mut>${h.label}</span><b>${h.text}</b></div>
     <div class=hbar><span style="width:${Math.max(0,Math.min(100,h.pct))}%;background:var(--${h.col})"></span></div>
   </div>`).join('');
 const tc=d.teaching||{rows:[]};
 $('teachsum').innerHTML=`<b class=neg>${tc.refuse_n||0}</b> losers gated OFF · <b class=pos>${tc.trade_n||0}</b> allowed to trade · realized book <b class="${(tc.total_pl||0)>=0?'pos':'neg'}">${money(tc.total_pl)}</b> — cut index/metal class (<span class=neg>${money(tc.idx_class_pl)}</span>) → book flips to <b class="${(tc.book_if_cut||0)>=0?'pos':'neg'}">${money(tc.book_if_cut)}</b>`;
 const ttb=$('teach').querySelector('tbody');
 ttb.innerHTML=(tc.rows||[]).map(r=>{
   const gate=r.act?'<span class="pill ok">▲ TRADE</span>':'<span class="pill bad">■ REFUSE</span>';
   const plw=Math.min(100,Math.abs(r.broker_pl)/10);   // £1000 -> full bar
   const plc=r.broker_pl>=0?'var(--grn)':'var(--red)';
   const wrc=r.act?'var(--grn)':'var(--red)';
   return `<tr><td class=mono>${r.instrument}</td>
     <td class="${r.broker_pl>=0?'pos':'neg'}">${money(r.broker_pl)}
       <div class=mbar><span style="width:${plw}%;background:${plc}"></span></div></td>
     <td class="${r.broker_exp>=0?'pos':'neg'}">${(r.broker_exp>=0?'+':'')+r.broker_exp}</td>
     <td>${(r.win_rate*100).toFixed(1)}%
       <div class=wbar><span style="width:${Math.min(100,r.win_rate*100)}%;background:${wrc}"></span></div></td>
     <td class="${r.expectancy>=0?'pos':'neg'}">${(r.expectancy>=0?'+':'')+r.expectancy}</td>
     <td>${gate}</td></tr>`}).join('')||'<tr><td colspan=6 class=mut>no taught brains with broker history</td></tr>';
 const hv=d.hours||{rows:[],cur_hour:-1};
 const hcell=(m,isCur)=>{
   const col=m>1?'rgba(34,197,94,'+Math.min(.85,(m-1)*0.9+.25)+')':m<1?'rgba(239,68,68,'+Math.min(.85,(1-m)*0.9+.2)+')':'#182338';
   const br=isCur?'2px solid var(--cy)':'1px solid #1b2740';
   return `<div title="×${m}" style="flex:1;min-width:22px;height:26px;border:${br};border-radius:4px;background:${col};display:flex;align-items:center;justify-content:center;font-size:10px;color:#dbe6ff">${m!==1?('×'+m):''}</div>`};
 const hhead='<div style="display:flex;gap:2px;margin-bottom:2px"><div style="width:64px"></div>'+Array.from({length:24},(_,h)=>`<div style="flex:1;min-width:22px;text-align:center;font-size:9px;color:${h===hv.cur_hour?'var(--cy)':'var(--dim)'}">${h}</div>`).join('')+'</div>';
 $('hours').innerHTML=hhead+(hv.rows||[]).map(r=>
   `<div style="display:flex;gap:2px;margin-bottom:3px;align-items:center"><div class=mono style="width:64px;font-size:11px">${r.instrument}</div>`+
   r.mults.map((m,h)=>hcell(m,h===hv.cur_hour)).join('')+'</div>').join('');
 const eq=d.equity||{pts:[]};
 (function(){
   const p=eq.pts||[]; if(p.length<2){$('equity').innerHTML='<div class=mut>waiting for fills…</div>';return;}
   const W=1120,H=90,lo=eq.min,hi=eq.max,rng=(hi-lo)||1;
   const x=i=>i*(W/(p.length-1)), y=v=>H-6-((v-lo)/rng)*(H-12);
   const line=p.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
   const area=`M0,${H} L`+p.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' L')+` L${W},${H} Z`;
   const up=eq.delta>=0, col=up?'var(--grn)':'var(--red)';
   $('equity').innerHTML=`<div class=row style="border:0;padding:0"><span class=mut>last ${p.length} fills</span>
     <b>£${eq.last.toLocaleString()} <span class="${up?'pos':'neg'}">(${up?'+':''}${eq.delta})</span></b></div>
     <svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio=none style="margin-top:4px">
       <defs><linearGradient id=eg x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="${col}" stop-opacity=.25/><stop offset=1 stop-color="${col}" stop-opacity=0/></linearGradient></defs>
       <path d="${area}" fill="url(#eg)"/><path d="${line}" fill=none stroke="${col}" stroke-width=2 stroke-linejoin=round/>
       <circle cx="${x(p.length-1).toFixed(1)}" cy="${y(p[p.length-1]).toFixed(1)}" r=3 fill="${col}"/></svg>`;
 })();
 const ph=d.pot_health||{},sc=d.scalp||{tape:[]};
 const recon=ph.recon?`${ph.recon.ago_s!=null?ph.recon.ago_s+'s ago':ph.recon.ts} · freed ${money(ph.recon.freed_gbp)} · cleared ${ph.recon.removed}`:'—';
 $('scalprow').innerHTML=`
  <div class=card><h2>♻️ Pot self-healing</h2>
    <div class=row><span class=mut>committed</span><b>${money(ph.committed)} / ${money(ph.cap)} (${ph.pct}%)</b></div>${bar(ph.pct,ph.pct>90?'var(--red)':'var(--gold)')}
    <div class=row style="margin-top:6px"><span class=mut>positions released (total)</span><b>${(ph.released_count||0).toLocaleString()}</b></div>
    <div class=row><span class=mut>last reconcile</span><b class=ok>${recon}</b></div>
    <div class=mut style="margin-top:4px">release-on-close + 2-min reconcile → orphans can't clog the cap</div></div>
  <div class=card><h2>⚡ Today's scalps</h2>
    <div class="big ${sc.pnl_today>=0?'pos':'neg'}">${(sc.pnl_today>=0?'+':'')+money(sc.pnl_today)}</div>
    <div class=mut>${sc.wins_today}/${sc.closes_today} wins · ${sc.wr_today}% win rate today</div>${bar(sc.wr_today,'var(--grn)')}</div>`;
 const ttb2=$('tape').querySelector('tbody');
 ttb2.innerHTML=(sc.tape||[]).map(t=>`<tr><td class=mono>${t.ts}</td><td class=mono>${t.instrument}</td>
   <td class="${t.pnl>=0?'pos':'neg'}">${(t.pnl>=0?'+':'')+t.pnl}</td><td class=mut>${t.reason}</td></tr>`).join('')||'<tr><td colspan=4 class=mut>no closes recorded yet this session</td></tr>';
 const pot=d.pot,fl=d.flow,ps=d.positions,pn=d.pnl;
 const venueBars=Object.entries(pot.by_venue||{}).map(([v,g])=>
   `<div class=row><span class=mut>${v}</span><b>${money(g)}</b></div>${bar(100*g/(pot.cap_gbp||1),'var(--blu)')}`).join('');
 $('top').innerHTML=`
  <div class=card><h2>Fleet</h2><div class=big>${d.fleet_alive}</div><div class=mut>belief-driven traders alive</div>
    <div class=row style="margin-top:8px"><span class=mut>event bus</span><b class="${d.bus_bound?'ok':'bad'}">${d.bus_bound?'LIVE':'DOWN'}</b></div></div>
  <div class=card><h2>Capital pot</h2><div class=big>${money(pot.committed_gbp)}</div>
    <div class=mut>of ${money(pot.cap_gbp)} committed (${pot.pct}%)</div>${bar(pot.pct,pot.pct>85?'var(--red)':'var(--gold)')}
    <div style="margin-top:8px">${venueBars}</div></div>
  <div class=card><h2>Today order flow</h2>
    <div class=row><span class=mut>placed</span><b class=pos>${fl.placed}</b></div>
    <div class=row><span class=mut>blocked</span><b class=neg>${fl.blocked}</b></div>
    <div style="margin-top:6px" class=mut>block reasons</div>${kv(fl.reasons)}</div>
  <div class=card><h2>Realized PnL</h2><div class="big ${pn.pnl_sum>=0?'pos':'neg'}">${(pn.pnl_sum>=0?'+':'')+pn.pnl_sum}</div>
    <div class=mut>${pn.wins}/${pn.closes} wins · as of ${pn.as_of}</div></div>`;
 const topPos=(ps.top||[]).map(p=>`<div class=row><span class=mut>${p.worker}<br><span class=pill>${p.instrument} · ${p.venue}</span></span><b>${money(p.notional_gbp)}</b></div>`).join('');
 $('mid').innerHTML=`
  <div class=card><h2>Open positions (${ps.count})</h2>${kv(ps.by_venue)}
    <div style="margin-top:6px" class=mut>exposure by ccy (£)</div>${kv(ps.by_ccy_notional)}</div>
  <div class=card><h2>Top positions by size</h2>${topPos||'<div class=mut>none</div>'}</div>
  <div class=card><h2>Active workers today</h2>${kv(fl.workers)}</div>`;
 const tb=$('recent').querySelector('tbody');
 tb.innerHTML=(fl.recent||[]).map(r=>`<tr><td class=mono>${(r.ts||'').slice(11)}</td><td>${r.worker||''}</td><td>${r.venue||''}</td><td>${r.side||''}</td>
   <td class="${r.ok?'ok':'bad'}">${r.ok?'✓ placed':'✕ '+(r.reason||'blocked')}</td></tr>`).join('');
}
tick();setInterval(tick,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data"):
            body = json.dumps(build_data()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8863)
    a = ap.parse_args()
    print(f"agentic traders dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
