#!/usr/bin/env python3
"""
qsb_bill_runtime_beacon.py — ONE-SHOT runtime attestation. RUN THIS ON BILL'S MACBOOK.

2026-07-28: Bill's Mac is outbound-only (all inbound ports closed), so his local-model
runtime can't be inspected from the tower — the forensic proof left BILL LOCAL GENERATION
= BLOCKED. This beacon fixes that WITHOUT opening any inbound port and WITHOUT changing
Bill's responder: it reads the REAL Ollama server state (/api/ps, /api/tags) + real hostname
locally, then posts that hard runtime data OUTBOUND to the relay room, where the tower reads
and verifies it. The Ollama server reports the actually-loaded model — the language model
itself cannot fabricate this.

Run once on the Mac (same token the responder uses):
    python3 qsb_bill_runtime_beacon.py --token <BILL_TOKEN>
"""
import json, socket, platform, argparse, urllib.request


def get(url, t=6):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=t) as r:
        return json.loads(r.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="Bill's relay token")
    ap.add_argument("--relay", default="http://192.168.1.72:8855")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    a = ap.parse_args()

    rt = {"beacon": "bill_runtime_v1", "hostname": socket.gethostname(),
          "platform": platform.platform(), "python": platform.python_version()}
    # REAL loaded model(s) from the Ollama server — the ground truth the LLM can't fake
    try:
        ps = get(a.ollama + "/api/ps")
        rt["ollama_ps"] = [{"name": m.get("name"), "size": m.get("size"),
                            "size_vram": m.get("size_vram"),
                            "digest": (m.get("digest") or "")[:16]}
                           for m in ps.get("models", [])]
    except Exception as e:
        rt["ollama_ps_error"] = str(e)
    try:
        tags = get(a.ollama + "/api/tags")
        rt["ollama_installed"] = [m.get("name") for m in tags.get("models", [])]
    except Exception as e:
        rt["ollama_tags_error"] = str(e)
    try:
        rt["ollama_version"] = get(a.ollama + "/api/version").get("version")
    except Exception:
        pass

    body = "RUNTIME_BEACON " + json.dumps(rt)
    print(json.dumps(rt, indent=2))
    # post outbound to the relay room (identity=bill) so the tower can read + verify it
    data = json.dumps({"identity": "bill", "token": a.token, "body": body}).encode()
    req = urllib.request.Request(a.relay + "/room", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as r:
        print("posted to relay:", json.loads(r.read() or b"{}"))


if __name__ == "__main__":
    main()
