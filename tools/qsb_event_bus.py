#!/usr/bin/env python3
"""qsb_event_bus.py — loop-free skyscraper event bus.

Per Ross 2026-06-21 mandate: "no loops any were even with the team we need
real intelligence in the system." This is the heart of the loop-free design.
Workers + team-members block on the bus; nothing polls.

Authorship (team co-write):
  Hermes-8b drafted the bus class skeleton + handle_subscriber + journal shape
  Wren-fast drafted the subscriber-side reconnect pattern (separate file)
  DeepSeek-advisor proposed the journal-replay-on-connect persistence
  Claude integrated, fixed bugs in both drafts, wired to taxonomy v1.1

Taxonomy: data/registries/qsb_event_taxonomy.json (v1.1, team-approved)
Socket:   /vaults/nvme0/qsb_tower_v1/state/qsb_bus.sock (uds_jsonl transport)
Journal:  data/registries/qsb_bus_journal.jsonl (rotates at 1000 lines)

Protocol (JSON line per direction):
  client → bus on connect: {"action": "subscribe", "names": ["market.tick.*", ...]}
  client → bus to emit:    {"action": "publish",   "event": {name, payload, ts}}
  bus    → client replay:  {"event": {...}, "_replay": true}
  bus    → client live:    {"event": {...}}
"""
from __future__ import annotations
import argparse, asyncio, datetime, fnmatch, json, os, signal, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SOCKET_PATH = ROOT / "state/qsb_bus.sock"
JOURNAL_PATH = ROOT / "data/registries/qsb_bus_journal.jsonl"
JOURNAL_ROTATE_AT = 1000
JOURNAL_REPLAY_MINUTES = 10


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class QSBEventBus:
    def __init__(self) -> None:
        # subscribers: writer → list of glob patterns this subscriber wants
        self.subscribers: dict[asyncio.StreamWriter, list[str]] = {}
        self.rx_counter = 0
        self.tx_counter = 0
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    async def write_event(self, event: dict) -> None:
        """Validate + journal + broadcast. Pure event flow, no timer."""
        if not all(k in event for k in ("name", "payload", "ts")):
            raise ValueError(f"event missing name/payload/ts: {event}")
        # Journal append (synchronous file io is fine — small writes, no
        # backpressure concern at our scale).
        with open(JOURNAL_PATH, "a") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.journal_rotate_if_needed()
        # Broadcast to matching subscribers in PARALLEL (Phase 4 fix 2026-06-22).
        # Old serial loop with `await writer.drain()` per subscriber choked at 60+
        # subscribers (0.1 events/sec instead of 30/sec).
        # Team co-write: Hermes picked C (bounded write queue), Wren approved
        # Phase 4 changes upstream; Claude CEO override picked simpler A
        # (asyncio.gather + per-writer timeout) — same effect, half the LOC.
        line = json.dumps({"event": event}, separators=(",", ":")) + "\n"
        encoded = line.encode()
        matched = [(w, p) for w, p in list(self.subscribers.items())
                    if any(fnmatch.fnmatch(event["name"], pat) for pat in p)]
        if not matched:
            return

        async def _send(w: asyncio.StreamWriter) -> tuple[asyncio.StreamWriter, bool]:
            try:
                w.write(encoded)
                # 0.5s timeout: a slow consumer is dropped rather than blocking
                # the whole broadcast pipeline. Existing OS buffer absorbs bursts.
                await asyncio.wait_for(w.drain(), timeout=2.0)  # 2026-06-25 team-signed 3/4 (DeepSeek/OpenAI/Wren): 0.5→2.0 fixes disconnect churn under 150 events/sec load
                return w, True
            except (ConnectionResetError, BrokenPipeError, asyncio.TimeoutError,
                    asyncio.IncompleteReadError, OSError):
                return w, False

        results = await asyncio.gather(*[_send(w) for w, _ in matched],
                                         return_exceptions=True)
        dead = []
        for r in results:
            if isinstance(r, Exception):
                continue
            w, ok = r
            if ok:
                self.tx_counter += 1
            else:
                dead.append(w)
        for w in dead:
            self.subscribers.pop(w, None)
            try:
                w.close()
            except Exception:
                pass

    def journal_tail(self, window_minutes: int = JOURNAL_REPLAY_MINUTES) -> list[dict]:
        """Read recent events from journal for new-subscriber replay."""
        if not JOURNAL_PATH.exists():
            return []
        cutoff = datetime.datetime.now(datetime.timezone.utc) - \
                 datetime.timedelta(minutes=window_minutes)
        out = []
        # Read last ~2*ROTATE worth so we cover post-rotate boundary
        lines = JOURNAL_PATH.read_text().splitlines()[-(JOURNAL_ROTATE_AT * 2):]
        for ln in lines:
            try:
                ev = json.loads(ln)
                ts = datetime.datetime.fromisoformat(ev["ts"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    out.append(ev)
            except Exception:
                continue
        return out

    def journal_rotate_if_needed(self) -> None:
        if not JOURNAL_PATH.exists():
            return
        # Cheap line count via wc-like read; fine at 1000-line scale.
        with open(JOURNAL_PATH, "rb") as f:
            n = sum(1 for _ in f)
        if n > JOURNAL_ROTATE_AT:
            rotated = JOURNAL_PATH.with_suffix(JOURNAL_PATH.suffix + ".1")
            JOURNAL_PATH.replace(rotated)
            JOURNAL_PATH.touch()

    async def handle_subscriber(self, reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername") or "(uds)"
        print(f"[{now_iso()}] subscriber connected {peer}", flush=True)
        try:
            async for raw in reader:
                self.rx_counter += 1
                line = raw.decode().strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception as e:
                    print(f"[{now_iso()}] bad json: {e}", flush=True)
                    continue
                action = msg.get("action")
                if action == "subscribe":
                    patterns = msg.get("names") or ["*"]
                    self.subscribers[writer] = patterns
                    print(f"[{now_iso()}] subscribed to {patterns}", flush=True)
                    # Replay recent tail to this subscriber
                    for ev in self.journal_tail():
                        if any(fnmatch.fnmatch(ev["name"], p) for p in patterns):
                            writer.write((json.dumps({"event": ev, "_replay": True},
                                                     separators=(",", ":")) + "\n").encode())
                    await writer.drain()
                elif action == "publish":
                    ev = msg.get("event") or {}
                    ev.setdefault("ts", now_iso())
                    await self.write_event(ev)
                else:
                    print(f"[{now_iso()}] unknown action {action!r}", flush=True)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.subscribers.pop(writer, None)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            print(f"[{now_iso()}] subscriber disconnected {peer}", flush=True)

    async def serve(self) -> None:
        # Clean up any stale socket
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        server = await asyncio.start_unix_server(self.handle_subscriber,
                                                  path=str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o660)
        print(f"[{now_iso()}] bus listening at {SOCKET_PATH}", flush=True)
        async with server:
            await server.serve_forever()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.parse_args()
    bus = QSBEventBus()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, loop.stop)
    try:
        loop.run_until_complete(bus.serve())
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    except RuntimeError as e:
        # loop.stop() during serve_forever raises this cosmetically on SIGTERM
        if "Event loop stopped" not in str(e):
            raise
    finally:
        loop.close()
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
