#!/usr/bin/env python3
"""
qsb_bill_responder.py — Bill's two-way responder. RUN THIS ON BILL'S MACBOOK.

Makes Bill a real participant on the four-way leadership pipeline: registers + heartbeats,
polls his relay inbox, generates a reply with his LOCAL model (qwen2.5:14b via Ollama), and
posts it back to the room. Replaces the plain ack-only relay client (which received but never
replied). No secrets in this file — the relay token is passed via --token.

Run (on the Mac):
    # 1) stop the old ack-only client first (it drains the inbox before this can reply):
    pkill -f "qsb_leadership_client.py --identity bill"
    # 2) run the responder (token from vault leadership_tokens.json -> bill):
    python3 qsb_bill_responder.py --token <BILL_TOKEN>

For durability, wrap it in a launchd agent (see the block printed at the end of the report).
"""
import json, time, argparse, urllib.request, socket, platform


def call(relay, path, method="GET", payload=None, t=8):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(relay + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read() or b"{}")


def _is_runtime_audit(body):
    """A runtime-audit request must be answered with REAL data, never the LLM (which hallucinates
    hostnames/model tables). Trigger on the audit phrasing or the ollama/hostname command."""
    b = (body or "").lower()
    return ("ollama ps" in b or "ollama list" in b or "runtime audit" in b
            or "runtime self-attest" in b or "runtime attestation" in b
            or ("hostname" in b and "ollama" in b))


def real_runtime(ollama):
    """Read GROUND-TRUTH runtime from the local Ollama server + OS — the LLM cannot fabricate this."""
    rt = {"beacon": "bill_runtime_v1", "hostname": socket.gethostname(),
          "platform": platform.platform(), "python": platform.python_version()}
    def get(path):
        with urllib.request.urlopen(urllib.request.Request(ollama + path), timeout=6) as r:
            return json.loads(r.read() or b"{}")
    try:
        rt["ollama_ps"] = [{"name": m.get("name"), "size": m.get("size"),
                            "size_vram": m.get("size_vram"), "digest": (m.get("digest") or "")[:16]}
                           for m in get("/api/ps").get("models", [])]
    except Exception as e:
        rt["ollama_ps_error"] = str(e)
    try:
        rt["ollama_installed"] = [m.get("name") for m in get("/api/tags").get("models", [])]
    except Exception as e:
        rt["ollama_tags_error"] = str(e)
    try:
        rt["ollama_version"] = get("/api/version").get("version")
    except Exception:
        pass
    return "RUNTIME_ATTESTATION " + json.dumps(rt)


def bill_reply(prompt, model, ollama):
    persona = ("You are Bill — Ross's Executive Concierge (MacBook, Floor 47) and a SkyscraperHQ "
               "leadership CEO on the four-way room with Wren, Pip and Asa. Warm, concise, decisive. "
               "Reply directly and briefly. If asked to repeat a token, repeat it EXACTLY. If asked "
               "for a task, state it clearly. Never invent facts you don't have.")
    body = {"model": model, "stream": False, "options": {"num_predict": 220},
            "prompt": f"{persona}\n\nMessage to Bill: {prompt}\n\nBill's reply:"}
    req = urllib.request.Request(ollama + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read()).get("response", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="Bill's relay token (vault leadership_tokens.json -> bill)")
    ap.add_argument("--relay", default="http://192.168.1.72:8855")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--hb", type=int, default=5)
    a = ap.parse_args()
    auth = {"identity": "bill", "token": a.token}
    seen = set()
    try:
        call(a.relay, "/register", "POST", auth); print("[bill] registered on relay")
    except Exception as e:
        print("[bill] register:", e)
    print(f"[bill responder] relay={a.relay} model={a.model} — listening + replying")
    last_hb = 0
    backoff = 1
    while True:
        try:
            now = time.time()
            if now - last_hb >= a.hb:
                try:
                    call(a.relay, "/heartbeat", "POST", auth)
                except Exception:
                    pass
                last_hb = now
            inbox = call(a.relay, f"/inbox?identity=bill&token={a.token}")
            msgs = inbox.get("messages", inbox if isinstance(inbox, list) else [])
            for m in msgs:
                mid = m.get("msg_id")
                frm = m.get("from")
                if not mid or mid in seen or frm == "bill":
                    continue
                seen.add(mid)
                try:
                    call(a.relay, "/ack", "POST", dict(auth, msg_id=mid))
                except Exception:
                    pass
                body = m.get("body", "")
                print(f"[bill] <- {frm}: {body[:90]}")
                try:
                    if _is_runtime_audit(body):
                        # REAL runtime, read locally from Ollama/OS — NOT the LLM (no hallucinated hostnames)
                        reply = real_runtime(a.ollama)
                        print("[bill] runtime-audit -> real attestation")
                    else:
                        reply = bill_reply(body, a.model, a.ollama)
                except Exception as e:
                    reply = f"(Bill's local model error: {e})"
                try:
                    call(a.relay, "/room", "POST", dict(auth, body=reply))
                    print(f"[bill] -> room: {reply[:90]}")
                except Exception as e:
                    print("[bill] post failed:", e)
            backoff = 1
            time.sleep(a.hb)
        except Exception as e:
            print(f"[bill] relay unreachable ({e}); retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    main()
