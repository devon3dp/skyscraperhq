#!/usr/bin/env python3
"""
qsb_bill_responder.py — Bill's two-way responder + REAL on-Mac skills. RUN THIS ON BILL'S MACBOOK.

Makes Bill a real participant on the four-way leadership pipeline: registers + heartbeats,
polls his relay inbox, and replies. Beyond plain text-gen (qwen2.5:14b via Ollama), Bill now
has REAL capabilities that run LOCALLY ON HIS MAC and report genuine local results outbound
through the relay (:8855) — never hallucinated. No secrets in this file — the relay token is
passed via --token.

REAL on-Mac skills (all read/write the Mac's own state):
  1. PERSISTENT LOCAL MEMORY   ~/.qsb_bill/memory.jsonl — Bill remembers past interactions,
                               recalls them, stores/forgets facts. Prepended to every prompt.
  2. SYSTEM/RUNTIME            hostname, os/uname, uptime, disk free, CPU count, Ollama version
                               + loaded + installed models. Read from the machine, not the LLM.
  3. LOCAL WORKSPACE           ~/.qsb_bill/ notes: list / read / save real files.
  4. SAFE LOCAL COMMAND        whitelist-only read-only shell (date, hostname, uptime, df -h,
                               sw_vers, ls ~/.qsb_bill, ollama list, ollama ps). Refuses others.
  5. MULTI-MODEL               "use model <tag>" answers with a different installed Ollama model.

Fail-closed + honest: if a skill can't run, Bill says so plainly — never fabricates.

Run (on the Mac):
    # 1) stop the old ack-only client first (it drains the inbox before this can reply):
    pkill -f "qsb_leadership_client.py --identity bill"
    # 2) run the responder (token from vault leadership_tokens.json -> bill):
    python3 qsb_bill_responder.py --token <BILL_TOKEN>

Self-test (proves every skill with REAL local output, no relay needed):
    python3 qsb_bill_responder.py --selftest

For durability, wrap it in a launchd agent (see the block printed at the end of the report).
"""
import json, time, argparse, urllib.request, socket, platform, os, shutil, subprocess, sys

# ---------------------------------------------------------------------------
# Local store paths (on the Mac these live under the Mac's home dir).
# ---------------------------------------------------------------------------
HOME = os.path.expanduser("~")
QSB_DIR = os.path.join(HOME, ".qsb_bill")
MEMORY_PATH = os.path.join(QSB_DIR, "memory.jsonl")
WORKSPACE = QSB_DIR  # notes live directly in the workspace dir
MEMORY_CONTEXT_N = 6  # how many past entries to prepend to the prompt

# Whitelist of read-only base commands Bill may actually run on the Mac.
# Keyed by the base command; value is the argv template (already safe/read-only).
SAFE_COMMANDS = {
    "date": ["date"],
    "hostname": ["hostname"],
    "uptime": ["uptime"],
    "df": ["df", "-h"],
    "sw_vers": ["sw_vers"],
    "ls": ["ls", QSB_DIR],
    "ollama": None,  # special: only "ollama list" / "ollama ps" allowed (handled below)
}


def _ensure_dir():
    os.makedirs(QSB_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. PERSISTENT LOCAL MEMORY
# ---------------------------------------------------------------------------
def mem_load(n=MEMORY_CONTEXT_N):
    """Return the last n memory entries (list of dicts), oldest-first. Real file read."""
    if not os.path.exists(MEMORY_PATH):
        return []
    out = []
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out[-n:]


def mem_append(entry):
    """Append one entry to memory.jsonl. Real file write. Returns the entry."""
    _ensure_dir()
    entry = dict(entry)
    entry.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(MEMORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def mem_count():
    return len(mem_load(n=10 ** 9))


def mem_forget():
    """Clear all memory. Returns how many entries were removed."""
    n = mem_count()
    if os.path.exists(MEMORY_PATH):
        os.remove(MEMORY_PATH)
    return n


def mem_recall_text(n=MEMORY_CONTEXT_N):
    """Human-readable readback of real stored memory."""
    ents = mem_load(n=n)
    if not ents:
        return "Bill's memory is empty — nothing stored yet."
    lines = [f"Bill's memory ({mem_count()} entries total, last {len(ents)}):"]
    for e in ents:
        if "fact" in e:
            lines.append(f"  [{e.get('ts','?')}] FACT: {e['fact']}")
        else:
            frm = e.get("from", "?")
            msg = (e.get("message") or "")[:80]
            rep = (e.get("reply") or "")[:80]
            lines.append(f"  [{e.get('ts','?')}] {frm}: {msg!r} -> {rep!r}")
    return "\n".join(lines)


def mem_context_block(n=MEMORY_CONTEXT_N):
    """Compact context string prepended to the model prompt so Bill 'remembers'."""
    ents = mem_load(n=n)
    if not ents:
        return ""
    parts = []
    for e in ents:
        if "fact" in e:
            parts.append(f"- (remembered fact) {e['fact']}")
        else:
            parts.append(f"- {e.get('from','?')} said {(e.get('message') or '')[:120]!r}; "
                         f"Bill replied {(e.get('reply') or '')[:120]!r}")
    return "Bill's memory of recent interactions (most recent last):\n" + "\n".join(parts)


# ---------------------------------------------------------------------------
# 2. SYSTEM / RUNTIME
# ---------------------------------------------------------------------------
def _ollama_get(ollama, path, t=6):
    with urllib.request.urlopen(urllib.request.Request(ollama + path), timeout=t) as r:
        return json.loads(r.read() or b"{}")


def real_runtime(ollama):
    """Read GROUND-TRUTH runtime from the local Ollama server + OS — the LLM cannot fabricate this."""
    rt = {"beacon": "bill_runtime_v1", "hostname": socket.gethostname(),
          "platform": platform.platform(), "python": platform.python_version()}
    try:
        rt["ollama_ps"] = [{"name": m.get("name"), "size": m.get("size"),
                            "size_vram": m.get("size_vram"), "digest": (m.get("digest") or "")[:16]}
                           for m in _ollama_get(ollama, "/api/ps").get("models", [])]
    except Exception as e:
        rt["ollama_ps_error"] = str(e)
    try:
        rt["ollama_installed"] = [m.get("name") for m in _ollama_get(ollama, "/api/tags").get("models", [])]
    except Exception as e:
        rt["ollama_tags_error"] = str(e)
    try:
        rt["ollama_version"] = _ollama_get(ollama, "/api/version").get("version")
    except Exception:
        pass
    return "RUNTIME_ATTESTATION " + json.dumps(rt)


def _uptime_str():
    """Real uptime — try `uptime`, fall back to reading nothing rather than faking."""
    try:
        return subprocess.run(["uptime"], capture_output=True, text=True, timeout=6).stdout.strip()
    except Exception as e:
        return f"(uptime unavailable: {e})"


def system_status(ollama):
    """REAL machine diagnostics, read locally. Returns a dict of ground-truth facts."""
    st = {"beacon": "bill_system_v1",
          "hostname": socket.gethostname(),
          "platform": platform.platform(),
          "system": platform.system(),
          "release": platform.release(),
          "machine": platform.machine(),
          "python": platform.python_version(),
          "cpu_count": os.cpu_count(),
          "uptime": _uptime_str()}
    try:
        du = shutil.disk_usage(HOME)
        gb = 1024 ** 3
        st["disk_total_gb"] = round(du.total / gb, 1)
        st["disk_free_gb"] = round(du.free / gb, 1)
        st["disk_used_gb"] = round(du.used / gb, 1)
    except Exception as e:
        st["disk_error"] = str(e)
    try:
        st["ollama_version"] = _ollama_get(ollama, "/api/version").get("version")
    except Exception as e:
        st["ollama_version_error"] = str(e)
    try:
        st["ollama_loaded"] = [m.get("name") for m in _ollama_get(ollama, "/api/ps").get("models", [])]
    except Exception as e:
        st["ollama_loaded_error"] = str(e)
    try:
        st["ollama_installed"] = [m.get("name") for m in _ollama_get(ollama, "/api/tags").get("models", [])]
    except Exception as e:
        st["ollama_installed_error"] = str(e)
    return st


def system_status_text(ollama):
    st = system_status(ollama)
    return "SYSTEM_STATUS " + json.dumps(st)


# ---------------------------------------------------------------------------
# 3. LOCAL WORKSPACE (notes)
# ---------------------------------------------------------------------------
def _safe_note_path(name):
    """Confine note names to the workspace dir — no traversal."""
    name = os.path.basename((name or "").strip())
    if not name:
        return None
    return os.path.join(WORKSPACE, name)


def ws_list():
    """Real listing of the workspace dir (files only)."""
    _ensure_dir()
    try:
        return sorted(f for f in os.listdir(WORKSPACE)
                      if os.path.isfile(os.path.join(WORKSPACE, f)))
    except Exception as e:
        return [f"(list error: {e})"]


def ws_read(name):
    p = _safe_note_path(name)
    if not p:
        return None, "no note name given"
    if not os.path.exists(p):
        return None, f"no such note: {os.path.basename(p)}"
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read(), None
    except Exception as e:
        return None, str(e)


def ws_save(name, text):
    p = _safe_note_path(name)
    if not p:
        return None, "no note name given"
    _ensure_dir()
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(text if text is not None else "")
        return os.path.basename(p), None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# 4. SAFE LOCAL COMMAND (whitelist)
# ---------------------------------------------------------------------------
def run_safe(cmd):
    """Run a whitelisted read-only command on the Mac. Refuses anything not on the whitelist.
    Returns (output_str, ok_bool)."""
    cmd = (cmd or "").strip()
    if not cmd:
        return "refused: empty command", False
    parts = cmd.split()
    base = parts[0]
    if base == "ollama":
        sub = parts[1] if len(parts) > 1 else ""
        if sub not in ("list", "ps"):
            return f"refused: 'ollama {sub}' is not whitelisted (only list, ps)", False
        argv = ["ollama", sub]
    elif base in SAFE_COMMANDS and SAFE_COMMANDS[base] is not None:
        argv = SAFE_COMMANDS[base]
    else:
        allowed = ", ".join(sorted(list(SAFE_COMMANDS.keys())))
        return f"refused: '{base}' is not on Bill's whitelist. Allowed base commands: {allowed}", False
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        out = (p.stdout or "") + (p.stderr or "")
        return out.strip() or "(no output)", True
    except FileNotFoundError:
        return f"(command not installed on this machine: {argv[0]})", False
    except Exception as e:
        return f"(command error: {e})", False


# ---------------------------------------------------------------------------
# 5. MULTI-MODEL
# ---------------------------------------------------------------------------
def installed_models(ollama):
    try:
        return [m.get("name") for m in _ollama_get(ollama, "/api/tags").get("models", [])]
    except Exception:
        return []


def bill_reply(prompt, model, ollama, mem_ctx=""):
    persona = ("You are Bill — Ross's Executive Concierge (MacBook, Floor 47) and a SkyscraperHQ "
               "leadership CEO on the four-way room with Wren, Pip and Asa. Warm, concise, decisive. "
               "Reply directly and briefly. If asked to repeat a token, repeat it EXACTLY. If asked "
               "for a task, state it clearly. Never invent facts you don't have.")
    ctx = (mem_ctx + "\n\n") if mem_ctx else ""
    body = {"model": model, "stream": False, "options": {"num_predict": 220},
            "prompt": f"{persona}\n\n{ctx}Message to Bill: {prompt}\n\nBill's reply:"}
    req = urllib.request.Request(ollama + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read()).get("response", "").strip()


# ---------------------------------------------------------------------------
# Skill router — decides which REAL skill (if any) handles the message.
# Returns (reply_text, remember_bool). remember=False for pure recall/status so
# we don't pollute memory with meta-queries.
# ---------------------------------------------------------------------------
def _is_runtime_audit(body):
    b = (body or "").lower()
    return ("ollama ps" in b or "ollama list" in b or "runtime audit" in b
            or "runtime self-attest" in b or "runtime attestation" in b
            or ("hostname" in b and "ollama" in b))


def handle_message(body, model, ollama):
    """Route an inbound message to a REAL skill or to text-gen. Returns (reply, model_used)."""
    b = (body or "").strip()
    low = b.lower()

    # --- Memory skills ---
    if low.startswith("remember:") or low.startswith("remember "):
        fact = b.split(":", 1)[1].strip() if ":" in b else b[len("remember"):].strip()
        if fact:
            mem_append({"fact": fact})
            return f"Stored. Bill now remembers: {fact}", model
        return "Nothing to remember — give me a fact after 'remember:'.", model
    if "what do you remember" in low or low.strip() in ("recall", "recall.", "recall!") or low.startswith("recall"):
        return mem_recall_text(), model
    if low.strip().startswith("forget"):
        n = mem_forget()
        return f"Done — cleared {n} memory entr{'y' if n == 1 else 'ies'}. Bill's memory is now empty.", model

    # --- System / runtime skills ---
    if _is_runtime_audit(body):
        return real_runtime(ollama), model
    if "system status" in low or "your machine" in low or "diagnostics" in low or low.strip() == "status":
        return system_status_text(ollama), model

    # --- Safe local command ---
    if low.startswith("run:") or low.startswith("run "):
        cmd = b.split(":", 1)[1].strip() if ":" in b else b[len("run"):].strip()
        out, ok = run_safe(cmd)
        tag = "RAN" if ok else "REFUSED"
        return f"{tag} `{cmd}`:\n{out}", model

    # --- Workspace skills ---
    if "list my files" in low or low.strip() in ("list files", "ls"):
        files = ws_list()
        return ("Bill's workspace files:\n" + "\n".join(f"  {f}" for f in files)) if files \
            else "Bill's workspace is empty.", model
    if low.startswith("read note"):
        name = b[len("read note"):].strip()
        content, err = ws_read(name)
        if err:
            return f"Can't read note: {err}", model
        return f"Note {name!r}:\n{content}", model
    if low.startswith("save note"):
        rest = b[len("save note"):].strip()
        if ":" in rest:
            name, text = rest.split(":", 1)
            saved, err = ws_save(name.strip(), text.strip())
            if err:
                return f"Can't save note: {err}", model
            return f"Saved note {saved!r} ({len(text.strip())} chars) to Bill's workspace.", model
        return "Usage: save note <name>: <text>", model

    # --- Multi-model switch ---
    use_model = model
    if low.startswith("use model"):
        rest = b[len("use model"):].strip()
        # First whitespace token is the model tag (tags contain colons, e.g. llama3.2:latest),
        # the remainder is the message. "use model <tag>: <msg>" is tolerated too.
        toks = rest.split(None, 1)
        tag = (toks[0] if toks else "").rstrip(":")
        msg = (toks[1] if len(toks) > 1 else "").lstrip(": ").strip()
        if not msg:
            msg = "Hello — confirm which model you are, in one short line."
        avail = installed_models(ollama)
        # accept an exact tag, or a bare name that matches a "<name>:latest" / "<name>:*" install
        match = None
        if tag:
            if tag in avail:
                match = tag
            else:
                for a_m in avail:
                    if a_m == tag or a_m.split(":", 1)[0] == tag:
                        match = a_m
                        break
        if match:
            use_model = match
            body = msg  # answer the remainder with the chosen model
            low = msg.lower()
        else:
            return (f"I don't have model {tag!r} installed. My real installed models: "
                    + (", ".join(avail) if avail else "(none / Ollama unreachable)")), model

    # --- Default: text-gen with memory context ---
    try:
        reply = bill_reply(body, use_model, ollama, mem_ctx=mem_context_block())
    except Exception as e:
        reply = f"(Bill's local model error: {e})"
    return reply, use_model


# ---------------------------------------------------------------------------
# Relay plumbing
# ---------------------------------------------------------------------------
def call(relay, path, method="GET", payload=None, t=8):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(relay + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read() or b"{}")


# ---------------------------------------------------------------------------
# Self-test — proves every skill with REAL local output (no relay needed).
# ---------------------------------------------------------------------------
def selftest(ollama, model):
    print("=" * 70)
    print("BILL RESPONDER SELF-TEST — every skill runs LOCALLY on THIS box's real data")
    print(f"(store dir: {QSB_DIR})")
    print("=" * 70)
    results = []

    def check(name, ok, detail):
        results.append((name, ok))
        print(f"\n### {name}: {'PASS' if ok else 'FAIL'}")
        print(detail)

    # 1. Persistent local memory: store + recall round-trip
    try:
        before = mem_count()
        marker = f"selftest-fact-{int(time.time())}"
        r1, _ = handle_message(f"remember: {marker}", model, ollama)
        r2, _ = handle_message("what do you remember", model, ollama)
        after = mem_count()
        # also exercise the from/message/reply append path
        mem_append({"from": "selftest", "message": "ping", "reply": "pong"})
        ok = (marker in r2) and (after == before + 1)
        detail = (f"store reply: {r1}\n"
                  f"recall contains stored fact: {marker in r2}\n"
                  f"count {before} -> {after} (+1 expected)\n"
                  f"recall readback:\n{r2}")
        check("1. PERSISTENT LOCAL MEMORY (store+recall)", ok, detail)
    except Exception as e:
        check("1. PERSISTENT LOCAL MEMORY (store+recall)", False, f"exception: {e}")

    # 2. System / runtime status: real machine data
    try:
        st = system_status(ollama)
        ok = bool(st.get("hostname")) and st.get("cpu_count") and ("disk_free_gb" in st)
        detail = json.dumps(st, indent=2)
        check("2. SYSTEM/RUNTIME STATUS (real machine data)", ok, detail)
    except Exception as e:
        check("2. SYSTEM/RUNTIME STATUS (real machine data)", False, f"exception: {e}")

    # 3. Workspace: save + list + read round-trip
    try:
        note = "selftest_note.txt"
        content = f"hello from selftest at {time.time()}"
        rs, _ = handle_message(f"save note {note}: {content}", model, ollama)
        rl, _ = handle_message("list my files", model, ollama)
        rr, _ = handle_message(f"read note {note}", model, ollama)
        ok = (note in rl) and (content in rr)
        detail = f"save: {rs}\nlist:\n{rl}\nread:\n{rr}"
        check("3. LOCAL WORKSPACE (save+list+read)", ok, detail)
    except Exception as e:
        check("3. LOCAL WORKSPACE (save+list+read)", False, f"exception: {e}")

    # 4. Safe local command: whitelisted runs, non-whitelisted refuses
    try:
        good, ok_good = run_safe("date")
        bad, ok_bad = run_safe("rm -rf /")
        ok = ok_good and (not ok_bad) and good and "refused" in bad.lower()
        detail = (f"whitelisted `date` (ok={ok_good}): {good}\n"
                  f"non-whitelisted `rm -rf /` (ok={ok_bad}): {bad}")
        check("4. SAFE LOCAL COMMAND (whitelist enforce)", ok, detail)
    except Exception as e:
        check("4. SAFE LOCAL COMMAND (whitelist enforce)", False, f"exception: {e}")

    # 5. Multi-model: list real installed models
    try:
        models = installed_models(ollama)
        ok = isinstance(models, list) and len(models) > 0
        # exercise the router's "use model <bad>" honest-refusal path too
        bad_switch, _ = handle_message("use model no-such-model-xyz: hi", model, ollama)
        ok = ok and ("don't have" in bad_switch.lower())
        detail = (f"real installed models ({len(models)}): {', '.join(models) if models else '(none)'}\n"
                  f"bad-switch honest refusal: {bad_switch}")
        check("5. MULTI-MODEL (real installed list + honest refuse)", ok, detail)
    except Exception as e:
        check("5. MULTI-MODEL (real installed list + honest refuse)", False, f"exception: {e}")

    print("\n" + "=" * 70)
    n_pass = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"SUMMARY: {n_pass}/{len(results)} skills PASS")
    print("=" * 70)
    return n_pass == len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="Bill's relay token (vault leadership_tokens.json -> bill)")
    ap.add_argument("--relay", default="http://192.168.1.72:8855")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--hb", type=int, default=5)
    ap.add_argument("--selftest", action="store_true", help="Run every skill locally + print PASS/FAIL, then exit")
    a = ap.parse_args()

    if a.selftest:
        ok = selftest(a.ollama, a.model)
        sys.exit(0 if ok else 1)

    if not a.token:
        ap.error("--token is required (unless --selftest)")

    _ensure_dir()
    auth = {"identity": "bill", "token": a.token}
    seen = set()
    try:
        call(a.relay, "/register", "POST", auth); print("[bill] registered on relay")
    except Exception as e:
        print("[bill] register:", e)
    print(f"[bill responder] relay={a.relay} model={a.model} store={QSB_DIR} — listening + replying")
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
                    reply, used = handle_message(body, a.model, a.ollama)
                except Exception as e:
                    reply, used = f"(Bill skill error: {e})", a.model
                # remember the interaction (skip pure meta-queries to keep memory clean)
                low = (body or "").lower()
                is_meta = (low.startswith(("remember", "forget", "recall", "list my files",
                                           "read note", "save note", "run:", "run ",
                                           "list files", "ls"))
                           or "what do you remember" in low or "system status" in low
                           or _is_runtime_audit(body))
                if not is_meta:
                    try:
                        mem_append({"from": frm, "message": body, "reply": reply})
                    except Exception:
                        pass
                try:
                    call(a.relay, "/room", "POST", dict(auth, body=reply))
                    print(f"[bill] -> room ({used}): {reply[:90]}")
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
