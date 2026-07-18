#!/usr/bin/env python3
"""qsb_ceo_beacon.py — daemon: POST our identity to the CEO registry every N s.

Runs on each CEO node. Reads own name+url from env or args, POSTs to registry
every 30s. If registry down, keeps trying — resolver still falls back to cache.

Env:
  QSB_CEO_NAME       (e.g. hq_claude, wren, tp_pip, acer_cass)
  QSB_CEO_URL        (e.g. http://192.168.1.72:8850)
  QSB_CEO_REGISTRY   (e.g. http://145.241.225.163:9210)
  QSB_CEO_BEACON_S   (default 30)
"""
from __future__ import annotations
import argparse, datetime, json, os, subprocess, sys, time, urllib.error, urllib.request


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def get_mac(interface: str | None = None) -> str | None:
    try:
        out = subprocess.check_output(["ip", "-o", "link"], text=True, timeout=3)
        for line in out.splitlines():
            if interface and interface not in line:
                continue
            if "link/ether" in line:
                parts = line.split()
                idx = parts.index("link/ether")
                return parts[idx + 1]
    except Exception:
        return None
    return None


def post_beacon(registry: str, ceo: str, url: str, mac: str | None) -> tuple[bool, str]:
    body = json.dumps({"ceo": ceo, "url": url, "mac": mac, "ts": now_iso()}).encode()
    req = urllib.request.Request(
        registry.rstrip("/") + "/beacon", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, r.read().decode()[:200]
    except urllib.error.URLError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceo", default=os.environ.get("QSB_CEO_NAME"))
    ap.add_argument("--url", default=os.environ.get("QSB_CEO_URL"))
    ap.add_argument("--registry", default=os.environ.get("QSB_CEO_REGISTRY", "http://145.241.225.163:9210"))
    ap.add_argument("--sleep", type=float, default=float(os.environ.get("QSB_CEO_BEACON_S", "30")))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--iface", default=None)
    args = ap.parse_args()
    if not args.ceo or not args.url:
        print("[beacon] need --ceo and --url (or env)", file=sys.stderr)
        sys.exit(2)
    mac = get_mac(args.iface)
    print(f"[beacon] ceo={args.ceo} url={args.url} registry={args.registry} mac={mac}", flush=True)
    while True:
        ok, msg = post_beacon(args.registry, args.ceo, args.url, mac)
        print(f"[beacon] {now_iso()} ok={ok} {msg[:120]}", flush=True)
        if args.once:
            sys.exit(0 if ok else 1)
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
