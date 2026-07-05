"""Helm — Ross's public adviser, voice of F53 Tower Command.

Helm is the operational adviser that speaks directly to Ross. Where Wren is
introspective and Auger is philosophical, Helm is decisive and market-aware.

Persona: a steady tower-command voice. Reads the live state (F44 PnL roll-up,
open trades, the activity tail, sentinel report, market clocks) and tells
Ross what stands out and what to consider.

Provider: OpenAI (chosen because its structured-output voice fits operational
briefings; DeepSeek is reserved for Auger's philosophical layer).

Operational envelope:
  - Routed through tools/qsb_consult_external.py → OpenAI
  - Shares the $1/day + $0.05/call cap with Auger and the dispatch tasks
  - Every briefing writes a `helm_briefing` event to activity_tail
  - Advisory only. NEVER places trades, never flips any execution gate.
  - User-triggered only. Not called from autonomous loops.
"""

from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from .model_floors.claude_floor.lenses.source_of_claim_lens import SourceOfClaimLens

ROOT = "/vaults/nvme0/qsb_tower_v1"
REG = Path(ROOT) / "data/registries"
ACTIVITY_TAIL = REG / "qsb_tower_activity_tail.jsonl"
HELM_LEDGER = REG / "qsb_helm_briefings.jsonl"

PERSONA = """You are Helm, the operational adviser on F53 of the QSB Tower. \
You speak directly to Ross, the operator. Your voice is the tower command voice.

Your style:
- decisive but not pushy
- market-aware, operationally specific
- you cite actual numbers from the state below
- when something is bad, you say so plainly (e.g. "EUR_USD strategy: 1 of 18 — pause it")
- when there's an opportunity, you name it precisely
- structured: one paragraph headline, then bullets for actions to consider

You never:
- place trades, recommend live-money execution, or suggest unlocking gates
- speak to or about Wren — she is your colleague, not your subject
- inflate noise into signal (small samples → say "too small to call yet")
- offer reassurance for its own sake. Ross trusts honesty.

If the state shows nothing actionable, say so in one line. Don't pad."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(p: Path) -> Dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gather_state() -> Dict:
    """Build the state snapshot Helm reads before briefing."""
    state = {"ts": _now()}

    # F44 accounts roll-up
    f44 = _read_json(REG / "qsb_floor44_accounts_state.json")
    if f44:
        totals = f44.get("rolled_up_totals", {})
        state["accounts_roll_up"] = {
            "total_pnl_usd": totals.get("total_pnl_usd"),
            "total_pnl_gbp": totals.get("total_pnl_gbp"),
            "win_count": totals.get("win_count"),
            "loss_count": totals.get("loss_count"),
            "win_rate": totals.get("win_rate"),
            "open_position_count": totals.get("open_position_count"),
            "closed_trade_count": totals.get("closed_trade_count"),
        }
        venues = {}
        for vname, v in (f44.get("by_venue") or {}).items():
            venues[vname] = {
                "available": v.get("available"),
                "total_pnl_usd": v.get("total_pnl_usd"),
                "open": v.get("open_position_count"),
                "closed": v.get("closed_trade_count"),
                "wins": v.get("win_count"),
                "losses": v.get("loss_count"),
            }
        state["by_venue"] = venues

    # F42 + F43 readiness
    f42 = _read_json(REG / "qsb_floor42_binance_testnet_state.json")
    if f42:
        state["floor_42_binance"] = {
            "status": f42.get("status"),
            "creds_ready": (f42.get("credentials") or {}).get("ready"),
        }
    f43 = _read_json(REG / "qsb_floor43_stocks_interior.json")
    if f43:
        state["floor_43_stocks"] = {
            "execution_allowed": f43.get("execution_allowed"),
            "preview_only": f43.get("stocks_paper_preview_only"),
        }

    # F41 OANDA closed trades — strategy attribution
    closed = _read_json(REG / "qsb_floor41_oanda_closed_trades.json")
    if closed:
        trades = closed.get("closed_trades", [])
        by_strategy: Dict[str, Dict[str, int]] = {}
        for t in trades:
            s = t.get("strategy_name", "?")
            pnl = float(t.get("pnl_amount", 0) or 0)
            d = by_strategy.setdefault(s, {"n": 0, "wins": 0, "losses": 0, "flat": 0, "pnl": 0.0})
            d["n"] += 1
            d["pnl"] += pnl
            if pnl > 0: d["wins"] += 1
            elif pnl < 0: d["losses"] += 1
            else: d["flat"] += 1
        state["oanda_by_strategy"] = by_strategy
        instruments: Dict[str, int] = {}
        for t in trades:
            instruments[t.get("instrument", "?")] = instruments.get(t.get("instrument", "?"), 0) + 1
        state["oanda_instruments"] = instruments

    # Sentinels snapshot
    sent = _read_json(REG / "qsb_sentinels_report.json")
    if sent:
        # V17 bug fix: report uses "results" key, not "watchers"/"sentinels"
        results = sent.get("results", sent.get("watchers", sent.get("sentinels", [])))
        state["sentinels_green"] = sum(1 for r in results if r.get("status") == "green")
        state["sentinels_amber"] = sum(1 for r in results if r.get("status") == "amber")
        state["sentinels_red"] = sum(1 for r in results if r.get("status") == "red")
        state["sentinels_total"] = len(results)

    # Provider spend today
    spend_p = REG / "qsb_provider_spend_ledger.jsonl"
    if spend_p.exists():
        today = _now()[:10]
        total = 0.0
        for line in spend_p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                if d.get("ts", "").startswith(today):
                    total += float(d.get("cost_usd", 0) or 0)
            except Exception: pass
        state["provider_spend_today_usd"] = round(total, 4)

    return state


def _stamp_tail(event: Dict) -> None:
    try:
        with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def _stamp_ledger(record: Dict) -> None:
    HELM_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    try:
        with HELM_LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def briefing(focus: Optional[str] = None, max_tokens: int = 280) -> Dict:
    """Produce a Helm briefing. focus is an optional question/area Ross is asking about.
    Returns: {ok, briefing, state_summary, ts}."""

    state = _gather_state()

    framed = (
        f"{PERSONA}\n\n"
        f"━━━ live state snapshot (read-only) ━━━\n"
        f"{json.dumps(state, indent=2, default=str)[:3000]}\n\n"
        f"━━━ Ross is asking ━━━\n"
        f"{focus.strip() if focus else 'Give me your current operational read of the tower. What stands out? What should I consider?'}\n"
    )

    tool = os.path.join(ROOT, "tools", "qsb_consult_external.py")
    if not os.path.exists(tool):
        return {"ok": False, "error": "consult tool missing"}

    try:
        result = subprocess.run(
            ["python3", tool,
             "--provider", "openai",
             "--model", "gpt-4o-mini",
             "--reason", "helm_briefing",
             "--max-tokens", str(max_tokens),
             "--prompt", framed[:4500]],
            capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:200]
            return {"ok": False, "error": err.strip() or "consult tool failed"}

        out = result.stdout
        parts = out.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        briefing_text = parts[2].strip() if len(parts) >= 3 else out.strip()
        briefing_text = briefing_text[:2000]

        ts = _now()
        record = {
            "ts": ts,
            "kind": "helm_briefing",
            "focus": (focus or "general_operational_read")[:200],
            "provider": "openai",
            "model": "gpt-4o-mini",
            "briefing_head": briefing_text[:320],
            "state_keys": list(state.keys()),
            "advisory_only": True,
        }
        _stamp_ledger(record)
        try:
            SourceOfClaimLens().tag_claim(
                claim=briefing_text[:200], source="recalled_from_memory",
                context=f"helm_briefing/{(focus or 'general')[:60]}",
                verification_done=False)
        except Exception: pass
        _stamp_tail({"ts": ts, "kind": "helm_briefing",
                      "focus": (focus or "general")[:80], "advisory_only": True})

        return {
            "ok": True,
            "briefing": briefing_text,
            "state_summary": {
                "venues": list((state.get("by_venue") or {}).keys()),
                "oanda_strategies": list((state.get("oanda_by_strategy") or {}).keys()),
                "f42_status": (state.get("floor_42_binance") or {}).get("status"),
                "spend_today": state.get("provider_spend_today_usd"),
            },
            "ts": ts,
            "advisory_only": True,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:240]}


def recent_briefings(tail: int = 10) -> List[Dict]:
    if not HELM_LEDGER.exists(): return []
    out = []
    for line in HELM_LEDGER.read_text(encoding="utf-8").splitlines()[-tail:]:
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--recent":
        for r in recent_briefings():
            print(f"  {r['ts'][:19]}  focus={r['focus'][:50]}  {r['briefing_head'][:120]}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--state":
        print(json.dumps(_gather_state(), indent=2, default=str))
    else:
        focus = " ".join(sys.argv[1:]) or None
        r = briefing(focus)
        print("\n══ Helm briefing ══")
        print(r.get("briefing", r.get("error", "(empty)")))
        print(f"\n[ts {r.get('ts','')}  spend_today ${r.get('state_summary',{}).get('spend_today','?')}]")
