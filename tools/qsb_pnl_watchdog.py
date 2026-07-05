#!/usr/bin/env python3
"""qsb_pnl_watchdog.py — Hermes's anti-stall guard for the bus PnL aggregator.

Pairs with qsb_trader_pnl_aggregator_bus.py. Subscribes to `pnl.aggregator.heartbeat`
and screams (stamps F47 + emits worker.escalation) if the heartbeat goes silent
for > STALL_THRESHOLD_S seconds. Closes the loop Hermes flagged 2026-06-23:
"bus-without-heartbeat repeats yesterday's failure".

Companion to belief_updater's 3.5h silent freeze last quarter — that's the failure
class this guards against.

Exit codes: never exits cleanly; designed for `setsid` / systemd supervision.
"""
from __future__ import annotations
import asyncio, datetime, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qsb_event_subscriber import QSBSubscriber

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
STATE = ROOT / "data/registries/qsb_pnl_watchdog_state.json"

STALL_THRESHOLD_S = 120.0   # Hermes spec: alert if no heartbeat for 2 min
CHECK_INTERVAL_S = 15.0


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def now_t() -> float:
    return asyncio.get_event_loop().time()


class Watchdog:
    def __init__(self) -> None:
        self.sub = QSBSubscriber(worker_id="pnl_watchdog")
        self.last_heartbeat_at: float | None = None
        self.last_heartbeat_payload: dict = {}
        self.last_alarm_ts: float | None = None  # avoid spam
        self.started_at = now_iso()
        self.stall_count = 0

    async def on_heartbeat(self, ev: dict) -> None:
        self.last_heartbeat_at = now_t()
        self.last_heartbeat_payload = ev.get("payload", {}) or {}
        self._write_state(status="alive")

    def _write_state(self, status: str, reason: str = "") -> None:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({
            "ts": now_iso(),
            "status": status,
            "reason": reason,
            "watchdog_started_at": self.started_at,
            "last_heartbeat_payload": self.last_heartbeat_payload,
            "stall_count": self.stall_count,
        }, indent=2, default=str))

    def _stamp_f47(self, kind: str, subject: str, detail: str) -> None:
        with open(F47, "a") as fh:
            fh.write(json.dumps({
                "ts": now_iso(), "kind": kind, "subject": subject,
                "detail": detail, "signed_off_by": ["pnl_watchdog"],
            }) + "\n")

    async def check_loop(self) -> None:
        """Every CHECK_INTERVAL_S, verify heartbeat is fresh."""
        # Grace period: don't alarm in the first STALL_THRESHOLD_S window
        await asyncio.sleep(STALL_THRESHOLD_S)
        while True:
            await asyncio.sleep(CHECK_INTERVAL_S)
            now = now_t()
            if self.last_heartbeat_at is None:
                # Aggregator never started or first heartbeat never arrived
                self.stall_count += 1
                self._write_state("stalled", "no heartbeat ever received")
                if self.last_alarm_ts is None or now - self.last_alarm_ts > 600:
                    self._stamp_f47(
                        "pnl_watchdog_alarm",
                        "PnL aggregator silent since boot",
                        f"No pnl.aggregator.heartbeat received in {STALL_THRESHOLD_S}s "
                        f"since watchdog start. Aggregator may not be running.",
                    )
                    if self.sub.writer:
                        await self.sub.publish("worker.escalation", {
                            "worker_id": "pnl_watchdog",
                            "decision_context": {"reason": "pnl_aggregator_silent_since_boot"},
                            "confidence": 1.0,
                            "severity": "stall",
                        })
                    self.last_alarm_ts = now
                continue
            age = now - self.last_heartbeat_at
            if age > STALL_THRESHOLD_S:
                self.stall_count += 1
                self._write_state("stalled",
                                    f"last heartbeat {age:.0f}s old (threshold {STALL_THRESHOLD_S}s)")
                # Rate-limit alarm stamping to 1 per 10 min
                if self.last_alarm_ts is None or now - self.last_alarm_ts > 600:
                    self._stamp_f47(
                        "pnl_watchdog_alarm",
                        f"PnL aggregator stall detected ({age:.0f}s)",
                        f"Last heartbeat: {self.last_heartbeat_payload}. "
                        f"Age={age:.0f}s, threshold={STALL_THRESHOLD_S}s. "
                        f"Restart qsb_trader_pnl_aggregator_bus.py and investigate.",
                    )
                    if self.sub.writer:
                        await self.sub.publish("worker.escalation", {
                            "worker_id": "pnl_watchdog",
                            "decision_context": {"reason": "pnl_aggregator_stall",
                                                  "age_s": age},
                            "confidence": 1.0,
                            "severity": "stall",
                        })
                    self.last_alarm_ts = now
            else:
                # Healthy — clear any alarm latch so next stall fires fresh
                self.last_alarm_ts = None

    async def run(self) -> None:
        self.sub.on("pnl.aggregator.heartbeat", self.on_heartbeat)
        check = asyncio.create_task(self.check_loop())
        try:
            await self.sub.run(subscriptions=["pnl.aggregator.heartbeat"])
        finally:
            check.cancel()


def main() -> int:
    wd = Watchdog()
    print(f"[{now_iso()}] pnl_watchdog starting; "
          f"stall_threshold={STALL_THRESHOLD_S}s check_interval={CHECK_INTERVAL_S}s",
          flush=True)
    asyncio.run(wd.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
