#!/usr/bin/env python3
"""qsb_event_subscriber.py — client library for any worker/team-member.

Per Ross 2026-06-21 mandate: workers block on the bus, not on clocks. This
library makes that one-line for any worker:

    from tools.qsb_event_subscriber import QSBSubscriber
    sub = QSBSubscriber()
    sub.on("market.tick.binance", on_btc_tick)
    sub.on("market.tick.oanda", on_fx_tick)
    asyncio.run(sub.run(subscriptions=["market.tick.*", "trade.*"]))

Authorship (team co-write):
  Wren-fast drafted the QSBSubscriber class + reconnect pattern
  Hermes-8b agreed on JSON-line wire format (matches qsb_event_bus.py)
  Claude integrated, fixed bugs (undefined reader, wire-format mismatch)

Wire protocol matches qsb_event_bus.py. Decision trivium per Ross + DeepSeek:
callback returns "yes"/"no"/"escalate" — escalate auto-emits worker.escalation.
"""
from __future__ import annotations
import asyncio, datetime, json, os, sys
from pathlib import Path
from typing import Awaitable, Callable

SOCKET_PATH = Path("/vaults/nvme0/qsb_tower_v1/state/qsb_bus.sock")
SPILL_PATH = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_bus_spillover.jsonl")

EventCallback = Callable[[dict], Awaitable[str | None] | str | None]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class QSBSubscriber:
    def __init__(self, worker_id: str = "anonymous") -> None:
        self.worker_id = worker_id
        self.callbacks: dict[str, EventCallback] = {}
        self.writer: asyncio.StreamWriter | None = None
        self.reader: asyncio.StreamReader | None = None
        self.rx_counter = 0
        self.start_t = asyncio.get_event_loop().time() if asyncio._get_running_loop() else 0
        self._connect_t: float | None = None
        # 2026-06-25 team-signed (DeepSeek+OpenAI+Wren+claude): publish-level
        # reconnect requires remembering subscriptions for replay.
        self._last_subscriptions: list[str] = []
        # 2026-06-25 PHASE 2 fix (DeepSeek team-signed): publish counter +
        # spillover file so events never silently drop.
        self._pub_counter = 0
        self._spill_lock = asyncio.Lock() if asyncio._get_running_loop() else None

    def on(self, pattern: str, fn: EventCallback) -> None:
        """Register a callback for events matching `pattern` (fnmatch glob)."""
        self.callbacks[pattern] = fn

    async def _reconnect(self) -> None:
        """2026-06-25 PHASE 2 (DeepSeek-authored): open fresh unix socket
        + re-subscribe with stderr logging. Called by publish() when writer
        is dead. Doesn't restart the read loop — only the publish path.
        Read loop has its own outer reconnect in run()."""
        try:
            self.reader, self.writer = await asyncio.open_unix_connection(
                str(SOCKET_PATH))
            if self._last_subscriptions:
                sub_msg = {"action": "subscribe",
                            "names": self._last_subscriptions}
                self.writer.write(
                    (json.dumps(sub_msg, separators=(",", ":")) + "\n").encode())
                await asyncio.wait_for(self.writer.drain(), timeout=2.0)
            print(f"[QSB] {self.worker_id} reconnect OK", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[QSB] {self.worker_id} reconnect FAILED: {e}",
                   file=sys.stderr, flush=True)
            self.writer = None
            self.reader = None

    async def _write_spill(self, name: str, payload: dict) -> None:
        """Append event to spillover file on publish-failure. Never dropped."""
        try:
            SPILL_PATH.parent.mkdir(parents=True, exist_ok=True)
            entry = {"worker_id": self.worker_id, "name": name,
                      "payload": payload, "ts_spilled": now_iso()}
            # Best-effort lock — fall through if loop isn't running.
            if self._spill_lock is None:
                with open(SPILL_PATH, "a") as f:
                    f.write(json.dumps(entry, separators=(",", ":")) + "\n")
            else:
                async with self._spill_lock:
                    with open(SPILL_PATH, "a") as f:
                        f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except Exception as e:
            print(f"[QSB] {self.worker_id} CRITICAL spill failed: {e}",
                   file=sys.stderr, flush=True)

    async def publish(self, name: str, payload: dict) -> None:
        """Publish with 3 retries + spillover on total failure. Events are
        NEVER silently dropped — every publish either reaches the bus OR
        lands in qsb_bus_spillover.jsonl. 2026-06-25 PHASE 2 (DeepSeek+team).
        Counter every 100 publishes logged to stderr for liveness check."""
        msg = {"action": "publish", "event": {"name": name, "payload": payload,
                                                "ts": now_iso()}}
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
        self._pub_counter += 1
        if self._pub_counter % 100 == 0:
            print(f"[QSB] {self.worker_id} publish#{self._pub_counter} (last={name})",
                   file=sys.stderr, flush=True)
        # init spill lock lazily if missing
        if self._spill_lock is None:
            try:
                self._spill_lock = asyncio.Lock()
            except Exception:
                pass
        for attempt in range(3):
            if not self.writer:
                await self._reconnect()
                if not self.writer:
                    if attempt < 2:
                        await asyncio.sleep(0.1)
                    continue
            try:
                self.writer.write(data)
                await asyncio.wait_for(self.writer.drain(), timeout=2.0)
                return  # success
            except (ConnectionResetError, BrokenPipeError, OSError,
                    asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                self.writer = None
                self.reader = None
                if attempt < 2:
                    print(f"[QSB] {self.worker_id} publish attempt {attempt+1} "
                          f"failed: {e}", file=sys.stderr, flush=True)
                    await asyncio.sleep(0.1)
        # All 3 attempts failed — spill instead of silent drop
        print(f"[QSB] {self.worker_id} publish SPILL after 3 attempts: {name}",
               file=sys.stderr, flush=True)
        await self._write_spill(name, payload)

    async def _emit_alive(self) -> None:
        """Dead-man-switch heartbeat — fires on connect and on each event handled."""
        now = asyncio.get_event_loop().time()
        uptime = int(now - (self._connect_t or now))
        await self.publish("system.heartbeat.alive", {
            "daemon_pid": os.getpid(),
            "uptime_s": uptime,
            "rx_counter": self.rx_counter,
            "tx_counter": 0,
        })

    async def _dispatch(self, event: dict) -> None:
        import fnmatch
        name = event.get("name", "")
        for pattern, fn in self.callbacks.items():
            if not fnmatch.fnmatch(name, pattern):
                continue
            try:
                res = fn(event)
                if asyncio.iscoroutine(res):
                    res = await res
            except Exception as e:
                # Auto-escalate on raised exception
                await self.publish("worker.escalation", {
                    "worker_id": self.worker_id,
                    "decision_context": {"event_name": name,
                                          "exception": repr(e)[:200]},
                    "confidence": 0.0,
                    "severity": "exception",
                })
                continue
            if res == "escalate":
                await self.publish("worker.escalation", {
                    "worker_id": self.worker_id,
                    "decision_context": {"event_name": name},
                    "confidence": 0.5,
                    "severity": "self_reported",
                })

    async def _connect_once(self, subscriptions: list[str]) -> None:
        reader, writer = await asyncio.open_unix_connection(str(SOCKET_PATH))
        self.writer = writer
        self._connect_t = asyncio.get_event_loop().time()
        print(f"[{now_iso()}] {self.worker_id} connected to bus", flush=True)
        sub_msg = {"action": "subscribe", "names": subscriptions}
        writer.write((json.dumps(sub_msg, separators=(",", ":")) + "\n").encode())
        await writer.drain()
        await self._emit_alive()
        async for raw in reader:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            ev = msg.get("event")
            if not ev:
                continue
            self.rx_counter += 1
            await self._dispatch(ev)
            # Heartbeat is event-driven, not scheduled — emit every 50 events
            if self.rx_counter % 50 == 0:
                await self._emit_alive()

    async def run(self, subscriptions: list[str] | None = None) -> None:
        """Loop-free reconnect: block on connection, on disconnect backoff and
        retry. The `loop` here is RECONNECT supervision, not a business clock."""
        if subscriptions is None:
            subscriptions = list(self.callbacks.keys()) or ["*"]
        self._last_subscriptions = list(subscriptions)  # 2026-06-25 store for publish-reconnect
        backoff = 1.0
        while True:
            try:
                await self._connect_once(subscriptions)
                backoff = 1.0  # only reaches on graceful disconnect
            except (FileNotFoundError, ConnectionRefusedError, ConnectionResetError,
                    BrokenPipeError, OSError) as e:
                print(f"[{now_iso()}] disconnect ({e!r}); reconnect in {backoff:.0f}s",
                      flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                self.writer = None
