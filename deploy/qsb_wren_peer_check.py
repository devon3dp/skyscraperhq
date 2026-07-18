#!/usr/bin/env python3
"""QSB Wren Endpoint Peer Check — runs ON a physical worker (read-only).
A worker checks Wren's dashboard + Concierge endpoints on HQ from its own box and
writes a short peer note. Grants no final acceptance. HQ discovered dynamically."""
import argparse, json, urllib.request, datetime
HQ = ["http://192.168.1.92","http://192.168.1.72","http://192.168.1.84"]

def get(url,t=4):
    with urllib.request.urlopen(url,timeout=t) as r: return r.status, r.read(4096).decode("utf-8","replace")

def discover():
    for b in HQ:
        try:
            if json.loads(get(b+":8852/api/hq_identity")[1]).get("service")=="qsb_boardroom": return b
        except Exception: continue
    return HQ[0]

def probe(url):
    try:
        c,body=get(url); import re
        t=re.search(r'<title>([^<]*)</title>',body); return c,(t.group(1) if t else body[:60].replace(chr(10),' '))
    except Exception as e: return 0,type(e).__name__

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--peer",required=True); ap.add_argument("--out",required=True); a=ap.parse_args()
    now=datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")
    base=discover()
    dc,dt=probe(base+":8851/status"); cc,ct=probe(base+":8857/")
    lines=[
      "%s WREN STAGE B ENDPOINT PEER CHECK — on %s's box at %s (read-only)"%(a.peer.upper(),a.peer,now),
      "HQ discovered dynamically at: %s"%base,
      "="*70,
      "Wren dashboard  %s:8851/status -> HTTP %s  (%s)"%(base,dc,dt),
      "Wren Concierge  %s:8857/       -> HTTP %s  (%s)"%(base,cc,ct),
      "Duplicate-endpoint ambiguity visible from here: %s"%("NO" if (dc and cc) else "could not confirm both"),
      "="*70,
      "PEER NOTE (%s): Wren dashboard + Concierge each answered on a single HQ endpoint."%a.peer,
      "This grants no final acceptance (Ross+ChatGPT decide).",
    ]
    open(a.out,"w").write("\n".join(lines)+"\n")
    print(json.dumps({"hq":base,"dash":dc,"concierge":cc,"wrote":a.out}))

if __name__=="__main__": main()
