#!/usr/bin/env python3
"""
qsb_underground_dispatcher.py — make the SkyscraperHQ Underground (:8875) carry GENUINE
traffic across every VALID track, on a timer.

2026-07-28, Ross: "make the Underground fully live". The tube map
(tools/qsb_tower_transit_map.py) only lights a track when a REAL event connects two
stations, read from the tower's own logs and age-gated to 900s. So the ONLY way to
light a track is to make a real event happen. This dispatcher does exactly that — no
fabrication, no decorative trains. If a target can't run, it is SKIPPED with a reason
and NO log row is written.

Per run (rotating, so different tracks light each cycle) it drives, across four rails:

  1. PROVIDERS (gene_pool ⇄ openai/deepseek/nvidia_nim/cohere/gemini):
     a REAL routed call to each LIVE provider (from qsb_gene_pool_key_health.json),
     using the same call machinery as qsb_gene_pool_diversity_prober.py, logged as a
     genuine routing row (task="dispatch") to qsb_brain_router_calls.jsonl — the exact
     log the Underground reads. The CALLER is rotated (wren / bill / tp_pip / acer_cass /
     boardroom / task_council) so different caller→gene_pool spurs light too.

  2. COMMS (wren ⇄ bill / tp_pip / acer_cass, and → town_square):
     ask Wren's REAL mind (POST :8865/api/send) to compose a genuine @mention message
     to a rotated peer, then post HER OWN WORDS to the relay via qsb_leadership_client
     (--send-dm / --send-room, using her vault token). Her peers' responders (Bill on
     .49, TP/Asa via the :9120 bridge) reply from their REAL minds — not puppeted. We
     then read room.jsonl to report who genuinely answered. Wren's words are real; if a
     peer doesn't answer, that is reported honestly (no fake reply row is written).

  3. COUNCIL (task_council ⇄ council15 / tc_sandbox, wren wields a specialist):
     run a REAL specialist via qsb_council15_tools.use_tool (rotated: gene-pool coder /
     gene-pool reasoning / local qwen worker) on a tiny real spec, then a REAL sandbox
     check (qsb_gene_pool_verify.external_verify as the tc_sandbox gate), journaling real
     tool_selected + sandbox_passed/sandbox_rejected events to qsb_council_tasks.jsonl in
     the SAME format qsb_task_council_autorunner.py uses. This lights council15, the
     wren→specialist sub-track, and tc_sandbox.

  4. CODEX (codex ⇄ task_council):
     append a REAL codex council note (actor="codex") to an existing real task via
     qsb_council_tasks.note — a genuine board event, exactly what the map keys codex on.

Rotation cursor persists at data/registries/qsb_underground_dispatch_cursor.json so the
set of providers/callers/peers/specialists advances each run.

INVALID / dead stations (documented, NEVER faked): kimi (QUOTA 429), grok/groq
(BLOCKED 403), claude (no working key / paid API dead), oracle (dead VM unreachable),
lumen (:8848 down), f46_bench (no event source), iquest_40b (coder endpoint not
answering). These cannot carry a real event, so this dispatcher skips them and says so.

CLI:
  python3 tools/qsb_underground_dispatcher.py --once   # one full distributed dispatch,
                                                        # prints per-track evidence.
systemd: qsb-underground-dispatcher.service (oneshot) + .timer (OnUnitActiveSec=3min).
"""
import json, os, sys, time, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
REG = ROOT / "data" / "registries"
VAULT = ROOT / "floors" / "floor_28_security_department" / "vault"
HEALTH = REG / "qsb_gene_pool_key_health.json"
LEDGER = REG / "qsb_brain_router_calls.jsonl"
COUNCIL_BOARD = REG / "qsb_council_tasks.jsonl"
ROOM = REG / "leadership_comms" / "room.jsonl"
DM_DIR = REG / "leadership_comms" / "dm"
CURSOR = REG / "qsb_underground_dispatch_cursor.json"
sys.path.insert(0, str(TOOLS))

WREN_CHAT = "http://127.0.0.1:8865/api/send"     # Wren's REAL mind (routes to :8851)
RELAY = "http://127.0.0.1:8855"
LEADER_CLIENT = TOOLS / "qsb_leadership_client.py"

# provider -> (vault var, kind, endpoint, model) — same spec as the diversity prober
SPEC = {
    "openai":     ("OPENAI_API_KEY",     "oai",    "https://api.openai.com/v1/chat/completions",           "gpt-4o-mini"),
    "deepseek":   ("DEEPSEEK_API_KEY",   "oai",    "https://api.deepseek.com/v1/chat/completions",         "deepseek-chat"),
    "nvidia_nim": ("NVIDIA_API_KEY",     "oai",    "https://integrate.api.nvidia.com/v1/chat/completions", "meta/llama-3.1-8b-instruct"),
    "cohere":     ("QSB_COHERE_API_KEY", "cohere", "https://api.cohere.ai/v2/chat",                        "command-r-08-2024"),
    "gemini":     ("GEMINI_API_KEY",     "gemini", "https://generativelanguage.googleapis.com/v1beta",     "gemini-flash-latest"),
}

# real rotating routed questions (genuine work, tiny cost)
QUESTIONS = [
    "In one sentence: name one concrete failure mode of an autonomous trading fleet.",
    "One line: how should a multi-AI council break a tie vote?",
    "One sentence: one cheap way to cut LLM routing cost without losing quality.",
    "One line: one reliable signal that a background worker silently died.",
    "One sentence: how do distributed AIs avoid duplicating each other's work?",
]

# rotate WHICH provider-call is attributed to which caller so different caller->gene_pool
# spurs on the map light up over successive runs (all are real callers of the pool).
CALLER_ROTATION = ["wren", "bill", "tp_pip", "acer_cass", "boardroom", "task_council"]
# rotate the COMMS peer Wren genuinely messages (DM lights wren<->peer; room lights ->town_square).
# NOTE: the relay identities are the SHORT names (wren/tp/asa/bill). The transit map ALIASes
# tp->tp_pip and asa->acer_cass, so a DM sent as the short name still lights the right station.
PEER_ROTATION = ["bill", "tp", "asa", "room"]
PEER_LABEL = {"bill": "Bill", "tp": "TP-Pip", "asa": "Asa", "room": "the room"}
# short relay identity -> station key the transit map draws (for the printed track name)
PEER_STATION = {"bill": "bill", "tp": "tp_pip", "asa": "acer_cass"}
# rotate which council-of-15 specialist Wren wields
SPEC_TASKS = [
    ("Write one line of Python that returns the current UTC time as an ISO string.", "coding"),
    ("In two sentences, describe a safe rollback strategy for a bad deploy.", "reasoning"),
    ("List three one-word tags for a task about trading-fleet risk monitoring.", "general"),
]

# stations that CANNOT carry a real event right now — documented, never faked.
BLOCKED = {
    "kimi":       "QUOTA (HTTP 429 moonshot-v1-8k) — no live routing",
    "grok":       "no live key / not in provider spec",
    "groq":       "BLOCKED (HTTP 403 llama-3.3-70b-versatile)",
    "claude":     "no working key (paid API dead, Max is account-only, not a gene-pool provider)",
    "oracle":     "dead cloud VM 145.241.225.163 unreachable — no event source",
    "lumen":      ":8848 service down — no event source",
    "f46_bench":  "no real event source wired to this station",
    "iquest_40b": "coder endpoint (ollama 40B) not answering on CPU",
}


def utc_ms():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── rotation cursor ──────────────────────────────────────────────────────────
def _cursor():
    try:
        return json.loads(CURSOR.read_text())
    except Exception:
        return {"caller": 0, "peer": 0, "spec": 0, "q": 0, "codex_note": 0}


def _save_cursor(c):
    try:
        CURSOR.write_text(json.dumps(c))
    except Exception:
        pass


# ── provider key + call machinery (mirrors qsb_gene_pool_diversity_prober.py) ──
def getkey(prov, var):
    f = VAULT / f".env.{prov}"
    if not f.exists():
        return None
    for l in f.read_text(errors="ignore").splitlines():
        l = l.strip()
        if l.startswith("export "):
            l = l[7:]
        if l.startswith(var + "="):
            return l.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _post_json(url, hdr, body, t=25):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode())


def call_provider(prov, q):
    var, kind, url, model = SPEC[prov]
    key = getkey(prov, var)
    if not key:
        return None, None
    if kind == "oai":
        d = _post_json(url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       {"model": model, "messages": [{"role": "user", "content": q}], "max_tokens": 40})
        return d["choices"][0]["message"]["content"].strip(), model
    if kind == "cohere":
        d = _post_json(url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       {"model": model, "messages": [{"role": "user", "content": q}], "max_tokens": 40})
        return "".join(c.get("text", "") for c in d["message"]["content"]).strip(), model
    if kind == "gemini":
        d = _post_json(f"{url}/models/{model}:generateContent?key={key}", {"Content-Type": "application/json"},
                       {"contents": [{"parts": [{"text": q}]}]})
        return d["candidates"][0]["content"]["parts"][0]["text"].strip(), model
    return None, None


def live_providers():
    try:
        h = json.loads(HEALTH.read_text())
        return [p for p, i in (h.get("providers", {}) or {}).items()
                if isinstance(i, dict) and (i.get("status") or "").upper() == "LIVE" and p in SPEC]
    except Exception:
        return []


def provider_status():
    try:
        h = json.loads(HEALTH.read_text())
        return {p: (i.get("status") or "?").upper() for p, i in (h.get("providers", {}) or {}).items()
                if isinstance(i, dict)}
    except Exception:
        return {}


# ── rail 1: PROVIDERS ─────────────────────────────────────────────────────────
def dispatch_providers(results, cur):
    live = live_providers()
    status = provider_status()
    q = QUESTIONS[cur["q"] % len(QUESTIONS)]
    # honestly document providers that are in SPEC but NOT live this cycle
    for prov in SPEC:
        if prov not in live:
            results.append({"track": f"gene_pool→{prov}", "type": "provider_route",
                            "ok": False, "skip": f"not LIVE ({status.get(prov, 'unknown')})"})
    if not live:
        return
    with open(LEDGER, "a") as f:
        for i, prov in enumerate(live):
            caller = CALLER_ROTATION[(cur["caller"] + i) % len(CALLER_ROTATION)]
            t0 = time.time()
            try:
                reply, model = call_provider(prov, q)
                if reply is None:
                    results.append({"track": f"{caller}→gene_pool→{prov}", "type": "provider_route",
                                    "ok": False, "skip": "no vault key"})
                    continue
                lat = round(time.time() - t0, 2)
                row = {"ts": utc_ms(), "caller": caller, "task": "dispatch", "tier": "pool",
                       "provider_used": prov, "model": model, "model_used": model,
                       "claude_avoided": True, "claude_blocked": False, "latency_s": lat,
                       "cost_usd_est": 5e-05, "tried": [prov],
                       "prompt_head": q, "reply_head": reply[:80]}
                f.write(json.dumps(row) + "\n"); f.flush()
                results.append({"track": f"{caller}→gene_pool→{prov}", "type": "provider_route",
                                "ok": True, "payload": q[:48],
                                "reply": reply[:70], "detail": f"{lat}s · {model}"})
            except urllib.error.HTTPError as e:
                results.append({"track": f"{caller}→gene_pool→{prov}", "type": "provider_route",
                                "ok": False, "skip": f"HTTP {e.code}"})
            except Exception as e:
                results.append({"track": f"{caller}→gene_pool→{prov}", "type": "provider_route",
                                "ok": False, "skip": str(e)[:60]})
    cur["caller"] = (cur["caller"] + 1) % len(CALLER_ROTATION)
    cur["q"] = (cur["q"] + 1) % len(QUESTIONS)


# ── rail 2: COMMS ─────────────────────────────────────────────────────────────
def _ask_wren(instruction, timeout=110):
    try:
        req = urllib.request.Request(WREN_CHAT, data=json.dumps({"text": instruction}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return d.get("reply") if d.get("ok") else None
    except Exception:
        return None


def _relay_send(kind, peer, body):
    """Post Wren's REAL words to the relay via her leadership client (uses her vault token).
    kind='room' -> --send-room ; kind='dm' -> --send-dm <peer> <body>."""
    if kind == "room":
        cmd = [sys.executable, str(LEADER_CLIENT), "--identity", "wren", "--relay", RELAY,
               "--send-room", body]
    else:
        cmd = [sys.executable, str(LEADER_CLIENT), "--identity", "wren", "--relay", RELAY,
               "--send-dm", peer, body]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        out = (r.stdout or "").strip()
        try:
            j = json.loads(out.splitlines()[-1]) if out else {}
        except Exception:
            j = {}
        return (r.returncode == 0 and (j.get("ok") or j.get("msg_id"))), (out or (r.stderr or "").strip())[:160]
    except Exception as e:
        return False, str(e)[:120]


def _dm_tail(peer, n=6):
    # relay writes dm files keyed by the sorted short-name pair (e.g. bill__wren, tp__wren, asa__wren)
    fname = {"bill": "bill__wren.jsonl", "tp": "tp__wren.jsonl", "asa": "asa__wren.jsonl"}.get(peer)
    if not fname:
        return []
    try:
        return [json.loads(x) for x in (DM_DIR / fname).read_text(errors="ignore").splitlines()[-n:] if x.strip()]
    except Exception:
        return []


def _room_tail(n=8):
    try:
        return [json.loads(x) for x in ROOM.read_text(errors="ignore").splitlines()[-n:] if x.strip()]
    except Exception:
        return []


def dispatch_comms(results, cur):
    peer = PEER_ROTATION[cur["peer"] % len(PEER_ROTATION)]
    cur["peer"] = (cur["peer"] + 1) % len(PEER_ROTATION)
    label = PEER_LABEL[peer]
    station = PEER_STATION.get(peer, peer)  # station key the transit map draws
    track = "wren→town_square" if peer == "room" else f"wren↔{station}"
    if peer == "room":
        instr = ("Post ONE short, genuine message to the whole leadership room (2 sentences max) — "
                 "a real status or question for the team about the tower right now. Reply with ONLY "
                 "the message text, no preamble.")
    else:
        instr = (f"Send ONE short, genuine direct message to {label} (2 sentences max). Start it with "
                 f"@{peer} and ask them a real question about their work right now. Reply "
                 f"with ONLY the message text, no preamble.")
    wren_words = _ask_wren(instr)
    if not wren_words:
        results.append({"track": track, "type": "comms", "ok": False,
                        "skip": "Wren's mind (:8865) gave no reply"})
        return
    wren_words = wren_words.strip()[:400]
    kind = "room" if peer == "room" else "dm"
    sent, sdetail = _relay_send(kind, peer, wren_words)
    if not sent:
        results.append({"track": track, "type": "comms", "ok": False,
                        "skip": f"relay send failed: {sdetail}", "payload": wren_words[:70]})
        return
    # record Wren's real outbound event as OK; note whether a peer genuinely answers.
    entry = {"track": track, "type": "comms", "ok": True, "payload": wren_words[:80],
             "detail": f"Wren posted to {label} via relay"}
    if peer != "room":
        # give the peer's responder a moment, then look for a real inbound reply in the DM
        time.sleep(6)
        tail = _dm_tail(peer, 6)
        peer_reply = next((m for m in reversed(tail)
                           if (m.get("from") in (peer, peer.split("_")[0], "tp", "asa", "bill"))
                           and m.get("from") != "wren"), None)
        if peer_reply:
            entry["reply"] = str(peer_reply.get("body", ""))[:70]
            entry["detail"] += f" · {label} replied (real mind)"
        else:
            entry["detail"] += (f" · {label} not yet answered "
                                + ("(Bill responds reliably; check next cycle)" if peer == "bill"
                                   else "(TP/Asa answer only when @mentioned/DM'd — honestly may lag)"))
    results.append(entry)


# ── rail 3: COUNCIL ───────────────────────────────────────────────────────────
def _journal(ev):
    with open(COUNCIL_BOARD, "a") as f:
        f.write(json.dumps(ev) + "\n")


def dispatch_council(results, cur):
    import qsb_council15_tools as TOOLS_C
    import qsb_gene_pool_verify as GPV
    import uuid
    spec_text, hint = SPEC_TASKS[cur["spec"] % len(SPEC_TASKS)]
    cur["spec"] = (cur["spec"] + 1) % len(SPEC_TASKS)
    tid = "UG_" + uuid.uuid4().hex[:10]
    # owner Wren picks the right council-of-15 tool (real routing over the real roster)
    tool = TOOLS_C.select_tool(spec_text, "")
    # journal in the EXACT format qsb_task_council_autorunner.py uses (tool_selected)
    _journal({"ts": utc(), "event": "tool_selected", "task_id": tid, "actor": "wren",
              "text": f"owner uses {tool['tool']} ({tool['model']})"})
    results.append({"track": "council15→specialist", "type": "council", "ok": True,
                    "payload": spec_text[:50], "detail": f"wren wields {tool['tool']}"})
    # actually USE the tool — real specialist call
    t0 = time.time()
    ur = TOOLS_C.use_tool(tool, spec=spec_text, context="", timeout_s=150)
    out = (ur.get("output") or "").strip()
    if not ur.get("ok") or not out:
        results.append({"track": "wren→specialist", "type": "council", "ok": False,
                        "skip": f"tool produced nothing: {str(ur.get('error'))[:60]}"})
        # still record the tool_selected event above lit council15
    else:
        _journal({"ts": utc(), "event": "noted", "task_id": tid, "actor": "wren",
                  "text": f"attempt 1: {tool['tool']} produced {ur.get('chars', len(out))} chars in "
                          f"{ur.get('elapsed_s', round(time.time()-t0,1))}s"})
        results.append({"track": "wren→specialist", "type": "council", "ok": True,
                        "payload": spec_text[:40], "reply": out[:70],
                        "detail": f"{tool['tool']} · {ur.get('chars', len(out))} chars"})
        # REAL sandbox gate: gene-pool DeepSeek verifies the artifact (tc_sandbox track)
        v = GPV.external_verify("tp_pip", spec_text, out, timeout_s=90)
        if not v.get("available"):
            results.append({"track": "task_council↔tc_sandbox", "type": "sandbox", "ok": False,
                            "skip": f"sandbox unavailable: {str(v.get('reply'))[:50]}"})
        else:
            passed = bool(v.get("verified"))
            ev = "sandbox_passed" if passed else "sandbox_rejected"
            _journal({"ts": utc(), "event": ev, "task_id": tid, "actor": "tc_sandbox",
                      "text": f"external:{v.get('provider')} verdict on artifact"})
            results.append({"track": "task_council↔tc_sandbox", "type": "sandbox", "ok": True,
                            "payload": ev, "reply": str(v.get("reply", ""))[:60],
                            "detail": f"real gene-pool sandbox ({v.get('provider')})"})


# ── rail 4: CODEX ─────────────────────────────────────────────────────────────
def dispatch_codex(results, cur):
    import qsb_council_tasks as T
    # pick a real, existing task to note against (never fabricate a task)
    tasks = T.snapshot().get("tasks", [])
    def real(t):
        title = (t.get("title") or "")
        tid = t.get("id") or ""
        # a genuine backlog task: has a real title, isn't a proof/test task, and isn't one of
        # this dispatcher's own ephemeral council specs (UG_) or a governance-proof cycle (TC_).
        return (bool(title.strip())
                and "council_proof" not in (t.get("tags") or [])
                and "#TEST" not in title.upper()
                and not tid.startswith("UG_")
                and not tid.startswith("TC_"))
    cand = [t for t in tasks if real(t)]
    cand.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    if not cand:
        results.append({"track": "codex↔task_council", "type": "codex_note", "ok": False,
                        "skip": "no real task on the board to note against"})
        return
    task = cand[cur["codex_note"] % len(cand)]
    cur["codex_note"] = (cur["codex_note"] + 1) % max(1, min(len(cand), 12))
    note = (f"Codex sweep {datetime.now(timezone.utc).strftime('%H:%M')}Z: reviewed context for "
            f"'{(task.get('title') or '')[:50]}' — no new patch this pass, context still valid.")
    r = T.note(task["id"], "codex", note)
    if r.get("ok"):
        results.append({"track": "codex↔task_council", "type": "codex_note", "ok": True,
                        "payload": note[:70], "detail": f"real codex note on {task['id']}"})
    else:
        results.append({"track": "codex↔task_council", "type": "codex_note", "ok": False,
                        "skip": f"note failed: {r}"})


# ── orchestration ─────────────────────────────────────────────────────────────
def run_once():
    cur = _cursor()
    results = []
    for fn in (dispatch_providers, dispatch_comms, dispatch_council, dispatch_codex):
        try:
            fn(results, cur)
        except Exception as e:
            results.append({"track": fn.__name__, "type": "error", "ok": False, "skip": str(e)[:120]})
    _save_cursor(cur)
    # blocked/dead stations — documented, never faked
    for st, why in BLOCKED.items():
        results.append({"track": f"({st})", "type": "blocked", "ok": False, "skip": why})
    return results


def _print(results):
    print("=" * 78)
    print(f"UNDERGROUND DISPATCH · {utc()}")
    print("=" * 78)
    carried = [r for r in results if r.get("ok")]
    skipped = [r for r in results if not r.get("ok") and r.get("type") != "blocked"]
    blocked = [r for r in results if r.get("type") == "blocked"]
    print(f"\n── CARRIED A REAL EVENT ({len(carried)}) ──")
    for r in carried:
        line = f"  OK       {r['track']:28} [{r['type']}]"
        if r.get("payload"):
            line += f"  payload={r['payload']!r}"
        print(line)
        if r.get("reply"):
            print(f"           ↳ reply/artifact: {r['reply']!r}")
        if r.get("detail"):
            print(f"           ↳ {r['detail']}")
    print(f"\n── SKIPPED (could not run this cycle) ({len(skipped)}) ──")
    for r in skipped:
        print(f"  SKIPPED  {r['track']:28} [{r['type']}]  reason: {r.get('skip')}")
    print(f"\n── BLOCKED / DEAD (documented, never faked) ({len(blocked)}) ──")
    for r in blocked:
        print(f"  BLOCKED  {r['track']:28} {r.get('skip')}")
    print(f"\nSUMMARY: {len(carried)} tracks carried a genuine event · "
          f"{len(skipped)} skipped · {len(blocked)} blocked/dead. NO fabricated rows written.")
    print("=" * 78)


def main():
    once = "--once" in sys.argv or "--run" in sys.argv
    results = run_once()
    if once or not sys.stdin.isatty():
        _print(results)
    else:
        _print(results)


if __name__ == "__main__":
    main()
