#!/usr/bin/env python3
"""qsb_ceo_relay_client.py — poll our inbox on the CEO registry, deliver locally.

Runs on each CEO node. Every N s: GET /inbox?ceo=self&since=<last_ts>.
For each new message: append to local inbox file (JSONL), advance since cursor.

Env:
  QSB_CEO_NAME
  QSB_CEO_REGISTRY
  QSB_CEO_RELAY_LOCAL_INBOX  (default data/registries/qsb_relay_inbox_<name>.jsonl)
  QSB_CEO_RELAY_S            (default 5)
"""
from __future__ import annotations
import argparse, datetime, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fetch_inbox(registry: str, ceo: str, since: str) -> list[dict]:
    q = f"?ceo={ceo}" + (f"&since={since}" if since else "")
    req = urllib.request.Request(registry.rstrip("/") + "/inbox" + q)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            return data if isinstance(data, list) else []
    except Exception:
        return []


def send_relay(registry: str, to: str, frm: str, kind: str, body: str) -> tuple[bool, str]:
    payload = json.dumps({"to": to, "frm": frm, "kind": kind, "body": body}).encode()
    req = urllib.request.Request(
        registry.rstrip("/") + "/relay", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, r.read().decode()[:200]
    except Exception as e:
        return False, str(e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceo", default=os.environ.get("QSB_CEO_NAME"))
    ap.add_argument("--registry", default=os.environ.get("QSB_CEO_REGISTRY", "http://145.241.225.163:9210"))
    ap.add_argument("--local-inbox", default=None)
    ap.add_argument("--sleep", type=float, default=float(os.environ.get("QSB_CEO_RELAY_S", "5")))
    ap.add_argument("--send", action="store_true", help="one-shot: send a relay message and exit")
    ap.add_argument("--to", default=None)
    ap.add_argument("--frm", default=None)
    ap.add_argument("--kind", default="msg")
    ap.add_argument("--body", default=None)
    args = ap.parse_args()

    if args.send:
        if not (args.to and args.frm and args.body):
            print("[relay] --send needs --to --frm --body", file=sys.stderr)
            sys.exit(2)
        ok, msg = send_relay(args.registry, args.to, args.frm, args.kind, args.body)
        print(json.dumps({"ok": ok, "msg": msg[:200]}))
        sys.exit(0 if ok else 1)

    if not args.ceo:
        print("[relay] need --ceo", file=sys.stderr)
        sys.exit(2)

    inbox_path = Path(args.local_inbox or ROOT / f"data/registries/qsb_relay_inbox_{args.ceo}.jsonl")
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path = Path(f"/tmp/qsb_ceo_relay_cursor_{args.ceo}.txt")
    since = cursor_path.read_text().strip() if cursor_path.exists() else ""
    print(f"[relay] ceo={args.ceo} registry={args.registry} inbox={inbox_path} since={since or '(new)'}", flush=True)

    while True:
        msgs = fetch_inbox(args.registry, args.ceo, since)
        if msgs:
            with inbox_path.open("a") as f:
                for m in msgs:
                    f.write(json.dumps(m) + "\n")
            since = msgs[-1].get("ts", since)
            cursor_path.write_text(since)
            print(f"[relay] {now_iso()} delivered {len(msgs)} to {inbox_path.name}, since={since}", flush=True)
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
