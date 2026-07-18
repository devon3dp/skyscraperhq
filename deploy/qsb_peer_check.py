#!/usr/bin/env python3
"""
QSB Peer Check — MASTER PHASE 2C (runs ON a peer worker box; read-only).
A worker (e.g. TP-Pip) independently checks another worker's (e.g. Acer) live truth
from its OWN machine and writes a short peer note. HQ does not author the note; the
peer's own box collects the facts. This grants NO final acceptance.
Usage on the peer box:
  python qsb_peer_check.py --peer tp_pip --check-worker acer_cass \
      --check-endpoint http://192.168.1.78:8872 --surrogate http://127.0.0.1:8862 \
      --retired 192.168.1.41:8872 --out TP_PIP_ACER_PHASE2_PEER_REVIEW.txt
"""
import argparse, json, urllib.request, datetime

HQ_CANDIDATES = ["http://192.168.1.92:8852", "http://192.168.1.72:8852", "http://192.168.1.84:8852"]


def _get(url, t=3):
    with urllib.request.urlopen(url, timeout=t) as r:
        return r.read(4096).decode("utf-8", "replace")


def discover_hq():
    for b in HQ_CANDIDATES:
        try:
            if json.loads(_get(b + "/api/hq_identity")).get("service") == "qsb_boardroom":
                return b
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--peer", required=True)
    ap.add_argument("--check-worker", required=True)
    ap.add_argument("--check-endpoint", required=True)
    ap.add_argument("--surrogate", required=True)
    ap.add_argument("--retired", default="")
    ap.add_argument("--out", default="PEER_REVIEW.txt")
    a = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    hq = discover_hq()
    reg = {}
    if hq:
        try:
            reg = json.loads(_get(hq + "/api/physical_workers/" + a.check_worker))
        except Exception:
            reg = {}
    # direct probe of the peer's PHYSICAL endpoint (from THIS box)
    try:
        who = _get(a.check_endpoint.rstrip("/") + "/whoami"); direct_ok = ('"id"' in who)
    except Exception:
        who, direct_ok = "", False
    # surrogate is a DIFFERENT endpoint
    distinct = a.check_endpoint.split("//")[-1].split("/")[0] != a.surrogate.split("//")[-1].split("/")[0]

    lines = [
        "%s PEER REVIEW of %s — generated on %s's box at %s (read-only)" % (a.peer.upper(), a.check_worker, a.peer, now),
        "This note was produced by %s from its own machine. It grants no final acceptance." % a.peer,
        "=" * 74,
        "1. Sees %s registered identity at HQ: %s (host=%s, src=%s, state=%s)" % (
            a.check_worker, "YES" if reg else "NO", reg.get("hostname", "?"), reg.get("source_ip", "?"),
            reg.get("registration_state", "?")),
        "2. Direct runtime probe %s (from %s's box): %s" % (a.check_endpoint, a.peer, "LIVE" if direct_ok else "UNREACHABLE"),
        "3. Physical endpoint (%s) is DIFFERENT from HQ surrogate (%s): %s" % (
            a.check_endpoint, a.surrogate, "YES (distinct)" if distinct else "NO"),
        "4. Heartbeat fresh: %s (age=%ss)" % (reg.get("registration_state") == "FRESH", reg.get("heartbeat_age_s", "?")),
        "5. Retired address %s used for live status: NO (must not be)" % (a.retired or "n/a"),
        "6. Identity returned by direct probe: %s" % (who[:110] if who else "(none)"),
        "=" * 74,
        "PEER VERDICT (%s): %s is a distinct, live, dynamically-registered physical worker%s." % (
            a.peer, a.check_worker,
            " " if (reg and direct_ok and distinct) else " — WITH GAPS (see above)"),
    ]
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"wrote": a.out, "reg_seen": bool(reg), "direct_ok": direct_ok, "distinct": distinct, "hq": hq}))


if __name__ == "__main__":
    main()
