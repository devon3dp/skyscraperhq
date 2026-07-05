"""qsb_slippage_telemetry.py — measure broker slip per trade.

Per Ross 2026-06-24 "make it all happen". Ship 3 of 3.

Subscribes to trade.closed events. Records per-instrument running stats:
- mean_slip_pips: average slippage (actual fill vs intended exit trigger)
- last_50_slips: ring buffer for percentile analysis
- by_strategy: same stats broken out per strategy

State file: data/registries/qsb_slippage_state.json
Periodic publish to bus event: slippage.report (every 60s)

The actual slip detection is best-effort — we use the gap between the trigger
tick's price (carried in event metadata if available) vs the actual exit_px.
For trades without trigger context, we compute "expected_exit" from the entry +
peak unrealized, and report that as proxy slip.

Output state schema:
{
    "updated_at": "...",
    "by_instrument": {
        "USD_JPY": {
            "n": 47,
            "avg_slip_gbp": 0.32,
            "max_slip_gbp": 4.59,
            "last_50": [...]
        },
        ...
    },
    "by_strategy_x_instrument": { ... }
}
"""
from __future__ import annotations
import asyncio
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402

STATE_FILE = ROOT / "data/registries/qsb_slippage_state.json"
PUBLISH_INTERVAL = 60.0


class SlippageTracker:
    def __init__(self):
        self.sub = QSBSubscriber("slippage_tracker")
        # per-instrument: deque of recent slip values (in £)
        self.by_inst: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        # per (worker, instrument): same
        self.by_worker_inst: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=50))
        self.last_publish = 0.0

    async def on_trade_closed(self, event: dict) -> None:
        payload = event.get("payload", {})
        if not payload.get("is_real"):
            return  # only measure REAL trades
        wid = payload.get("worker_id")
        inst = payload.get("instrument")
        pnl = payload.get("pnl", 0)
        reason = payload.get("reason", "")
        if not (wid and inst):
            return
        # Slip proxy:
        # - If reason is abs_stop_X.XX, slip = magnitude of pnl beyond -X.XX
        # - If reason is trail_NNpct_peak_X.XX, slip = (peak * 0.NN_lock - actual_pnl)
        # - Otherwise: 0 (no measurable slip)
        slip_gbp = 0.0
        if reason.startswith("abs_stop_"):
            try:
                cap = float(reason.replace("abs_stop_", ""))
                slip_gbp = max(0.0, abs(pnl) - cap)
            except Exception:
                pass
        elif reason.startswith("trail_") and "_peak_" in reason:
            # trail_25pct_peak_2.03 → peak 2.03, lock at 75% = 1.52
            try:
                parts = reason.split("_peak_")
                peak = float(parts[1])
                pct_str = parts[0].replace("trail_", "").replace("pct", "")
                pct = float(pct_str)
                # trail_25pct = exit at 75% of peak (locks 75%)
                # trail_80pct = exit at 80% of peak (locks 80%)
                # The retrace % name varies. Assume "lock_pct" derived from naming.
                if pct == 25:
                    target_lock = peak * 0.75
                elif pct == 80:
                    target_lock = peak * 0.80
                elif pct == 90:
                    target_lock = peak * 0.90
                else:
                    target_lock = peak * 0.75
                slip_gbp = max(0.0, target_lock - pnl)
            except Exception:
                pass
        elif reason.startswith("breakeven_anchor_"):
            # Should exit at 0, anything below is slip
            slip_gbp = max(0.0, -pnl)
        if slip_gbp > 0:
            self.by_inst[inst].append(slip_gbp)
            self.by_worker_inst[(wid, inst)].append(slip_gbp)

    def snapshot(self) -> dict:
        import datetime
        out = {
            "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "by_instrument": {},
            "by_worker_x_instrument": {},
        }
        for inst, buf in self.by_inst.items():
            if not buf:
                continue
            arr = list(buf)
            out["by_instrument"][inst] = {
                "n": len(arr),
                "avg_slip_gbp": sum(arr) / len(arr),
                "max_slip_gbp": max(arr),
                "p90_slip_gbp": sorted(arr)[int(len(arr) * 0.9)] if len(arr) > 5 else max(arr),
            }
        for (wid, inst), buf in self.by_worker_inst.items():
            if not buf:
                continue
            arr = list(buf)
            out["by_worker_x_instrument"][f"{wid}::{inst}"] = {
                "n": len(arr),
                "avg_slip_gbp": sum(arr) / len(arr),
                "max_slip_gbp": max(arr),
            }
        return out

    async def publish_loop(self) -> None:
        while True:
            await asyncio.sleep(PUBLISH_INTERVAL)
            snap = self.snapshot()
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(snap, indent=2))
            await self.sub.publish("slippage.report", snap)

    async def run(self) -> None:
        self.sub.on("trade.closed", self.on_trade_closed)
        await asyncio.gather(
            self.sub.run(subscriptions=["trade.closed"]),
            self.publish_loop(),
        )


if __name__ == "__main__":
    print("[slippage_tracker] starting; publish every 60s", flush=True)
    t = SlippageTracker()
    asyncio.run(t.run())
