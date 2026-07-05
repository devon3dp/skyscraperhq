#!/usr/bin/env python3
"""qsb_team_chat.py — publish to the team-chat bus topic (Wren design 2026-06-23).

Cross-instrument trader chat channel. Any worker (or operator) can publish
insights/observations that other workers can subscribe to. NOT a control
channel — purely advisory team awareness.

Topic schema (Wren's spec):
  team.chat.<venue>           — venue-wide (oanda, binance, alpaca, tower)
  team.chat.<venue>.<instr>   — instrument-scoped

Payload:
  {worker_id, instrument, venue, message, timestamp}

Usage:
  python3 tools/qsb_team_chat.py --worker-id belief_driven_jpy \\
    --instrument USD_JPY --venue oanda \\
    --message "trending hard, raising my profit-take target"

Workers can also publish programmatically via QSBSubscriber.publish().
Dashboard reads from bus journal — see team_chat_recent() in
qsb_traders_live_serve.py.
"""
from __future__ import annotations
import argparse, asyncio, datetime, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qsb_event_subscriber import QSBSubscriber


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _persist_chat(payload: dict, topic: str) -> None:
    """Write directly to dedicated team_chat history (bus journal rotates fast)."""
    from pathlib import Path
    p = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_team_chat_history.jsonl")
    row = {
        "ts": payload.get("timestamp", ""),
        "topic": topic,
        "worker": (payload.get("worker_id") or "?").replace("belief_driven_", ""),
        "instrument": payload.get("instrument", ""),
        "venue": payload.get("venue", ""),
        "message": payload.get("message", ""),
    }
    with open(p, "a") as fh:
        fh.write(json.dumps(row) + "\n")


async def publish_chat(worker_id: str, instrument: str, venue: str,
                        message: str, scope: str = "venue") -> None:
    sub = QSBSubscriber(worker_id=worker_id)
    # Brief connect just to publish — uses subscriber's connection
    async def _do_publish():
        # Hijack the run() loop with a one-shot connect + publish
        from pathlib import Path
        import asyncio
        SOCKET = Path("/vaults/nvme0/qsb_tower_v1/state/qsb_bus.sock")
        reader, writer = await asyncio.open_unix_connection(str(SOCKET))
        # subscribe to nothing — just publish
        sub_msg = {"action": "subscribe", "names": []}
        writer.write((json.dumps(sub_msg) + "\n").encode())
        await writer.drain()
        topic = f"team.chat.{venue}"
        if scope == "instrument":
            topic = f"{topic}.{instrument}"
        payload = {"worker_id": worker_id, "instrument": instrument,
                    "venue": venue, "message": message, "timestamp": now_iso()}
        pub = {"action": "publish",
                "event": {"name": topic, "payload": payload, "ts": now_iso()}}
        writer.write((json.dumps(pub) + "\n").encode())
        await writer.drain()
        # Also persist to dedicated history (bus journal rotates fast)
        _persist_chat(payload, topic)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        print(f"published {topic} payload={payload}")
    await _do_publish()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--worker-id", required=True)
    p.add_argument("--instrument", default="*")
    p.add_argument("--venue", required=True, choices=["oanda", "binance", "alpaca", "tower"])
    p.add_argument("--message", required=True)
    p.add_argument("--scope", default="venue", choices=["venue", "instrument"])
    args = p.parse_args()
    asyncio.run(publish_chat(args.worker_id, args.instrument, args.venue,
                              args.message, args.scope))
    return 0


if __name__ == "__main__":
    sys.exit(main())
