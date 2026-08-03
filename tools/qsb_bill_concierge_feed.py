#!/usr/bin/env python3
"""
qsb_bill_concierge_feed.py — Bill's PROACTIVE concierge engine.

Goal (Ross 2026-07-29): make Bill a genuine proactive concierge. He watches the
tower and PUSHES what matters to Ross LIVE, without Ross asking — a periodic
briefing plus immediate event alerts.

HARD CONSTRAINT honoured here:
  Bill has ONE mind, on HIS Mac (qsb_bill_responder.py, qwen2.5:14b, relay :8855).
  This engine NEVER fabricates a tower-side "Bill mind." It:
    1. GATHERS real, noteworthy tower state (tower_health, task board, PnL/pot,
       gene pool, self-audit) — only REAL facts, never invented.
    2. DECIDES what is Ross-worthy (changes / problems / wins) vs noise, with a
       persisted state file so nothing is re-pushed (de-dupe + rate-limit).
    3. Hands the real facts to BILL over the relay (DM). Bill's own qwen composes
       the briefing in HIS voice; we read his reply back from the room.
    4. If Bill's mind can't compose in time (offline / model timeout / overloaded),
       we FALL BACK to delivering the raw facts as a plainly-labelled auto-summary
       — we do NOT fake Bill's voice.
    5. PUSHES the message to Ross on Telegram (proven-live channel:
       QSB Tower Reception bot, chat 8683680296), with dedupe so Ross isn't spammed.

Non-autonomous / honest:
  - This is a status-surfacing tick (like a monitoring probe), not a task loop.
  - Every push is gated on REAL change. Nothing fabricated. If a channel is
    unreachable, it says so and records honestly.

CLI:
  python3 tools/qsb_bill_concierge_feed.py --briefing        # periodic briefing (dedup/rate-limited)
  python3 tools/qsb_bill_concierge_feed.py --briefing --force # force a briefing now (ignore rate-limit)
  python3 tools/qsb_bill_concierge_feed.py --alerts          # event-alert scan (service down / red audit / big PnL / task milestone)
  python3 tools/qsb_bill_concierge_feed.py --tick            # alerts + (rate-limited) briefing — what the timer runs
  python3 tools/qsb_bill_concierge_feed.py --facts           # just print the gathered real facts (no send)
  python3 tools/qsb_bill_concierge_feed.py --dry-run ...     # compute + compose but do NOT push to Ross
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.parse, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
RUNTIME = ROOT / "data" / "runtime"
VAULT = ROOT / "floors" / "floor_28_security_department" / "vault"
sys.path.insert(0, str(ROOT / "tools"))

STATE_PATH = RUNTIME / "qsb_bill_concierge_state.json"
LOG_PATH = REG / "qsb_bill_concierge_feed.jsonl"
LEADER_TOKENS = VAULT / "leadership_tokens.json"
TELEGRAM_ENV = VAULT / ".env.telegram"

RELAY = os.environ.get("BILL_RELAY", "http://127.0.0.1:8855")
ROSS_CHAT_ID = "8683680296"   # Ross's chat with the QSB Tower Reception bot (proven live)

# Bill's Mac (his ONE mind). The relay room is the primary route to his mind, but it is
# shared/noisy — when the room round-trip times out we ask HIS SAME qwen on HIS Mac
# directly over SSH (still Bill's real mind, not a tower-side fake). Passwordless key.
BILL_MAC_SSH = os.environ.get("BILL_MAC_SSH", "rossknechtel@192.168.1.99")
BILL_OLLAMA = os.environ.get("BILL_OLLAMA", "http://127.0.0.1:11434")
BILL_MODEL = os.environ.get("BILL_MODEL", "qwen2.5:14b")
BILL_PERSONA = ("You are Bill — Ross's Executive Concierge (MacBook, Floor 47). "
                "Warm, concise, decisive. Reply in your own voice, briefly. "
                "Use ONLY the facts given; never invent anything.")

# Rate-limits (seconds)
BRIEFING_MIN_INTERVAL = 45 * 60     # don't push a routine briefing more than ~every 45min
ALERT_COOLDOWN = {                  # per-alert-key minimum gap so we never spam the same alert
    "service_down": 20 * 60,
    "self_audit_red": 30 * 60,
    "big_pnl": 30 * 60,
    "task_milestone": 30 * 60,
    "disk_high": 60 * 60,
}
# thresholds
BIG_PNL_MOVE_GBP = 25.0             # session PnL swing worth alerting Ross
DISK_HIGH_PCT = 90


# ── util ────────────────────────────────────────────────────────────────────

def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_epoch() -> float:
    return time.time()


def log(rec: dict) -> None:
    rec = {"ts": utc(), **rec}
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2))
    tmp.replace(STATE_PATH)


# ── 1. GATHER real tower facts ──────────────────────────────────────────────

def gather_facts() -> dict:
    """Collect REAL, noteworthy tower state. Every field is read from a live source;
    on any read failure the field is marked with an error string, never faked."""
    f: dict = {"ts": utc()}

    # tower health (services / traders / disk / load / task council)
    try:
        import qsb_tower_health as H
        s = H.snapshot()
        svc = s.get("services", {})
        tc = s.get("task_council") or {}
        f["health"] = {
            "services_up": svc.get("up"), "services_total": svc.get("total"),
            "services_down": svc.get("down", []),
            "bus_bound": s.get("event_bus_bound"),
            "traders_alive": s.get("traders_alive"),
            "disk_pct": s.get("root_disk_pct"),
            "load_1m": s.get("load_1m"),
            "tasks_open": tc.get("open"), "tasks_in_progress": tc.get("in_progress"),
            "tasks_blocked": tc.get("blocked"), "tasks_done": tc.get("done"),
        }
    except Exception as e:
        f["health"] = {"error": str(e)}

    # session PnL (today) + grand OANDA practice PnL
    try:
        sp = json.loads((REG / "qsb_session_pnl_stop.json").read_text())
        f["session_pnl"] = {
            "date": sp.get("session_date"), "realized_pnl": sp.get("realized_pnl"),
            "daily_cap": sp.get("daily_cap"), "tripped": sp.get("tripped"),
            "closes": sp.get("total_closes"),
        }
    except Exception as e:
        f["session_pnl"] = {"error": str(e)}
    try:
        osum = json.loads((REG / "qsb_oanda_history_summary.json").read_text())
        f["oanda_pnl_gbp"] = osum.get("grand_pl_gbp")
        f["oanda_fills"] = osum.get("fills_with_pl")
    except Exception as e:
        f["oanda_pnl_gbp"] = None
        f["oanda_err"] = str(e)

    # portfolio pot (capital committed)
    try:
        pot = json.loads((REG / "qsb_portfolio_pot.json").read_text())
        f["pot"] = {"committed_gbp": round(pot.get("committed_gbp", 0), 2),
                    "cap_gbp": pot.get("cap_gbp"),
                    "open_positions": len(pot.get("open_positions", {}))}
    except Exception as e:
        f["pot"] = {"error": str(e)}

    # self-audit findings (open, by severity)
    try:
        reds, ambers = [], []
        p = REG / "qsb_self_audit_findings.jsonl"
        if p.exists():
            # keep only the latest status per key
            latest: dict = {}
            for line in p.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                latest[d.get("key")] = d
            for d in latest.values():
                if d.get("status") == "open":
                    (reds if d.get("severity") == "red" else ambers).append(d.get("title", "?"))
        f["self_audit"] = {"red": reds, "amber_count": len(ambers), "amber": ambers[:5]}
    except Exception as e:
        f["self_audit"] = {"error": str(e)}

    # gene pool router health (uptime, autonomy)
    try:
        gp = json.loads((REG / "gene_pool_router_state.json").read_text())
        m = gp.get("metrics", {})
        f["gene_pool"] = {"uptime_s": m.get("uptime_s"), "events": m.get("events"),
                          "autonomy": (m.get("autonomy") or {}).get("enabled")}
    except Exception as e:
        f["gene_pool"] = {"error": str(e)}

    return f


# ── 2. DECIDE what is Ross-worthy (diff vs last state) ──────────────────────

def compute_alerts(facts: dict, state: dict) -> list[dict]:
    """Return a list of alert dicts {key, kind, text, cooldown_key} for REAL changes
    that Ross should know about immediately. Cooldown is enforced by the caller."""
    alerts = []
    h = facts.get("health") or {}
    prev = state.get("last_facts") or {}
    ph = prev.get("health") or {}

    # service down (new)
    down = set(h.get("services_down") or [])
    pdown = set(ph.get("services_down") or [])
    new_down = down - pdown
    if down:
        # alert if any service is down; cooldown keyed on the down-set
        alerts.append({
            "cooldown_key": "service_down",
            "dedup_key": "service_down:" + ",".join(sorted(down)),
            "kind": "service_down",
            "severity": "red",
            "text": f"Service(s) DOWN: {', '.join(sorted(down))} "
                    f"({h.get('services_up')}/{h.get('services_total')} up).",
        })

    # self-audit RED findings (new red keys)
    reds = (facts.get("self_audit") or {}).get("red") or []
    prev_reds = (prev.get("self_audit") or {}).get("red") or []
    new_reds = [r for r in reds if r not in prev_reds]
    if new_reds:
        alerts.append({
            "cooldown_key": "self_audit_red",
            "dedup_key": "self_audit_red:" + "|".join(sorted(new_reds))[:120],
            "kind": "self_audit_red",
            "severity": "red",
            "text": "Self-audit RED: " + "; ".join(new_reds[:3]),
        })

    # big session PnL move
    sp = facts.get("session_pnl") or {}
    psp = prev.get("session_pnl") or {}
    cur = sp.get("realized_pnl")
    old = psp.get("realized_pnl")
    if isinstance(cur, (int, float)) and isinstance(old, (int, float)):
        move = cur - old
        if abs(move) >= BIG_PNL_MOVE_GBP:
            direction = "up" if move > 0 else "down"
            alerts.append({
                "cooldown_key": "big_pnl",
                "dedup_key": f"big_pnl:{round(cur,1)}",
                "kind": "big_pnl",
                "severity": "amber",
                "text": f"Session PnL moved {direction} GBP {move:+.2f} "
                        f"(now GBP {cur:+.2f} today, cap {sp.get('daily_cap')}).",
            })
    if sp.get("tripped") and not psp.get("tripped"):
        alerts.append({
            "cooldown_key": "big_pnl",
            "dedup_key": "pnl_cap_tripped",
            "kind": "big_pnl",
            "severity": "red",
            "text": f"Daily loss cap TRIPPED at GBP {sp.get('realized_pnl')}. Trading paused.",
        })

    # task milestone (new dones)
    cur_done = h.get("tasks_done")
    old_done = ph.get("tasks_done")
    if isinstance(cur_done, int) and isinstance(old_done, int) and cur_done > old_done:
        alerts.append({
            "cooldown_key": "task_milestone",
            "dedup_key": f"task_done:{cur_done}",
            "kind": "task_milestone",
            "severity": "info",
            "text": f"Task board: {cur_done - old_done} new task(s) completed "
                    f"(now {cur_done} done, {h.get('tasks_open')} open).",
        })

    # disk high
    disk = h.get("disk_pct")
    try:
        disk_n = int(str(disk).rstrip("%")) if disk else None
    except Exception:
        disk_n = None
    if disk_n and disk_n >= DISK_HIGH_PCT:
        alerts.append({
            "cooldown_key": "disk_high",
            "dedup_key": f"disk_high:{disk_n}",
            "kind": "disk_high",
            "severity": "amber",
            "text": f"Root disk at {disk}% — running high.",
        })

    return alerts


# ── 3+4. Route facts through BILL's real Mac mind (or honest fallback) ───────

def _bill_token() -> str | None:
    try:
        return json.loads(LEADER_TOKENS.read_text()).get("tokens", {}).get("bill")
    except Exception:
        return None


def _wren_token() -> str | None:
    try:
        return json.loads(LEADER_TOKENS.read_text()).get("tokens", {}).get("wren")
    except Exception:
        return None


def _relay_get(path: str, t=6):
    with urllib.request.urlopen(RELAY.rstrip("/") + path, timeout=t) as r:
        return json.loads(r.read() or b"{}")


def bill_online() -> tuple[bool, str]:
    try:
        pres = _relay_get("/presence").get("presence", {})
        b = pres.get("bill", {})
        return bool(b.get("online")), b.get("last_heartbeat", "?")
    except Exception as e:
        return False, f"presence err: {e}"


def _room_lines_after(after_epoch: float) -> list[dict]:
    """Bill's room messages appended after we sent the prompt (best-effort by file tail)."""
    out = []
    p = REG / "leadership_comms" / "room.jsonl"
    try:
        lines = p.read_text(errors="replace").splitlines()
    except Exception:
        return out
    for line in lines[-80:]:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("from") == "bill":
            out.append(d)
    return out


def compose_via_bill_direct(facts_text: str, ask: str, timeout_s: int = 90) -> tuple[str, str]:
    """Secondary route to Bill's SAME mind: ask his qwen on his Mac directly over SSH.
    Used only when the shared relay room round-trip is contended/timed out. This is
    still Bill's real Mac + real model + concierge persona — not a tower-side fabrication.
    Returns (composed, "bill_mind_direct") or ("", "fallback:<reason>")."""
    import subprocess, shlex
    prompt = f"{BILL_PERSONA}\n\nFacts:\n{facts_text}\n\nTask: {ask}\n\nBill's reply:"
    body = json.dumps({"model": BILL_MODEL, "stream": False,
                       "options": {"num_predict": 130},
                       "prompt": prompt})
    # curl on the Mac -> local Ollama; parse the response field with python3 on the Mac.
    remote = (f"curl -s --max-time {timeout_s - 10} {BILL_OLLAMA}/api/generate "
              f"-d {shlex.quote(body)} "
              f"| python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"response\",\"\").strip())'")
    try:
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", BILL_MAC_SSH, remote],
            capture_output=True, text=True, timeout=timeout_s)
    except Exception as e:
        return "", f"fallback:ssh_direct_failed({e})"
    out = (p.stdout or "").strip()
    if p.returncode != 0 or not out:
        return "", f"fallback:direct_no_output(rc={p.returncode})"
    return out, "bill_mind_direct"


def compose_via_bill(facts_text: str, ask: str, wait_s: int = 75) -> tuple[str, str]:
    """Send the real facts to Bill (DM via relay), let HIS qwen compose, read his reply.
    Returns (composed_text, source) where source in {"bill_mind","fallback:<reason>"}.
    Correlates his reply by a unique nonce he is asked to echo. Never fabricates his voice."""
    online, last_hb = bill_online()
    if not online:
        return "", f"fallback:bill_offline(last_hb={last_hb})"
    wtok = _wren_token()
    if not wtok:
        return "", "fallback:no_relay_token"

    nonce = "BZ" + uuid.uuid4().hex[:8].upper()
    msg_id = "brief_" + uuid.uuid4().hex[:12]
    body = (f"[TOWER-FEED — automated concierge brief for Ross; this is the tower feeding you "
            f"REAL facts, compose in YOUR OWN voice as Ross's concierge] "
            f"Begin your reply with the tag {nonce} then {ask} "
            f"Use ONLY these facts, keep it warm, under 60 words:\n{facts_text}")
    payload = {"identity": "wren", "token": wtok, "to": "bill", "msg_id": msg_id, "body": body}
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(RELAY.rstrip("/") + "/dm", data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as e:
        return "", f"fallback:dm_send_failed({e})"

    sent = now_epoch()
    deadline = sent + wait_s
    while time.time() < deadline:
        time.sleep(4)
        for d in _room_lines_after(sent):
            b = d.get("body", "")
            if nonce in b:
                composed = b.split(nonce, 1)[1].strip(" :—-\n")
                if composed.startswith("(Bill's local model error"):
                    break  # his mind errored on the relay path — try the direct route
                if composed:
                    return composed, "bill_mind"
        else:
            continue
        break

    # Relay room path was contended / errored. Ask HIS SAME mind directly over SSH.
    composed, src = compose_via_bill_direct(facts_text, ask)
    if composed and not composed.startswith("("):
        return composed, src
    return "", src if src.startswith("fallback:") else "fallback:bill_timeout"


# ── facts → human text ──────────────────────────────────────────────────────

def facts_to_lines(facts: dict) -> list[str]:
    """Turn the gathered facts into concise fact-lines (used both to prompt Bill and
    as the honest fallback body)."""
    h = facts.get("health") or {}
    lines = []
    if "error" not in h:
        svc = f"{h.get('services_up')}/{h.get('services_total')} services up"
        if h.get("services_down"):
            svc += f" (DOWN: {', '.join(h['services_down'])})"
        lines.append(svc + f", bus {'LIVE' if h.get('bus_bound') else 'DEAD'}")
        lines.append(f"{h.get('traders_alive')} traders alive; disk {h.get('disk_pct')}, load {h.get('load_1m')}")
        lines.append(f"tasks: {h.get('tasks_open')} open, {h.get('tasks_in_progress')} in progress, "
                     f"{h.get('tasks_blocked')} blocked, {h.get('tasks_done')} done")
    sp = facts.get("session_pnl") or {}
    if "error" not in sp:
        rp = sp.get("realized_pnl")
        rp_s = f"{rp:+.2f}" if isinstance(rp, (int, float)) else str(rp)
        lines.append(f"today's PnL GBP {rp_s} (cap {sp.get('daily_cap')}, "
                     f"{sp.get('closes')} closes, tripped={sp.get('tripped')})")
    if facts.get("oanda_pnl_gbp") is not None:
        lines.append(f"OANDA practice grand PnL GBP {facts.get('oanda_pnl_gbp')} over {facts.get('oanda_fills')} fills")
    pot = facts.get("pot") or {}
    if "error" not in pot:
        lines.append(f"capital committed GBP {pot.get('committed_gbp')}/{pot.get('cap_gbp')} "
                     f"across {pot.get('open_positions')} open positions")
    sa = facts.get("self_audit") or {}
    if "error" not in sa:
        if sa.get("red"):
            lines.append("SELF-AUDIT RED: " + "; ".join(sa["red"][:3]))
        lines.append(f"self-audit: {len(sa.get('red',[]))} red, {sa.get('amber_count')} amber open")
    gp = facts.get("gene_pool") or {}
    if "error" not in gp:
        lines.append(f"gene pool up {int((gp.get('uptime_s') or 0)/3600)}h, autonomy={gp.get('autonomy')}")
    return lines


# ── 5. PUSH to Ross (Telegram, proven-live) ─────────────────────────────────

def _telegram_token() -> str | None:
    try:
        for line in TELEGRAM_ENV.read_text().splitlines():
            if line.startswith("QSB_TELEGRAM_BOT_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                return tok or None
    except Exception:
        pass
    return None


# 2026-07-29 Ross: "i don't want things sent to telegram — WhatsApp is what we use."
# Bill's concierge now delivers to Ross on WhatsApp via the Galaxy phone (tools/qsb_whatsapp_send.py,
# adb -> com.whatsapp). If the phone isn't connected via adb, it returns an HONEST not-delivered
# result (phone offline) — it does NOT silently fall back to Telegram.
ROSS_WHATSAPP = "+447481057362"


def push_to_ross(text: str) -> dict:
    """Deliver to Ross on WhatsApp via the Galaxy phone. Honest result; no Telegram fallback."""
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "qsb_whatsapp_send.py"),
             "--to", ROSS_WHATSAPP, "--text", text[:1000]],
            capture_output=True, text=True, timeout=60)
        out = (r.stdout or "").strip()
        # qsb_whatsapp_send.py emits a single PRETTY (multi-line, indented) JSON
        # object. Parse the WHOLE stdout, not just the last line — the last line
        # is only "}" which never parses and silently forced ok=False even when
        # the send physically succeeded. (2026-07-29 fix)
        res = {}
        if out:
            try:
                res = json.loads(out)
            except Exception:
                # fall back to scanning for the JSON object if extra lines leaked in
                s, e = out.find("{"), out.rfind("}")
                if s != -1 and e != -1 and e > s:
                    try:
                        res = json.loads(out[s:e + 1])
                    except Exception:
                        res = {}
        ok = (r.returncode == 0) and bool(res.get("ok") or res.get("sent"))
        return {"ok": ok, "channel": "whatsapp", "to": ROSS_WHATSAPP,
                "error": (None if ok else (res.get("error") or (r.stderr or out)[:160] or "whatsapp send failed")),
                "detail": res}
    except Exception as e:
        return {"ok": False, "channel": "whatsapp", "to": ROSS_WHATSAPP, "error": str(e)}


# ── message builders ────────────────────────────────────────────────────────

def build_briefing_message(facts: dict, composed: str, source: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    if source == "bill_mind":
        head = f"Bill (concierge) — {stamp}:"
        body = composed
    else:
        # honest fallback: Bill's mind unavailable; auto-summary from real facts
        reason = source.replace("fallback:", "")
        head = f"Tower concierge auto-brief — {stamp}  (Bill's Mac mind unavailable: {reason})"
        body = "\n".join("• " + l for l in facts_to_lines(facts))
    return f"{head}\n{body}"


def build_alert_message(alert: dict, composed: str, source: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    icon = {"red": "[RED]", "amber": "[AMBER]", "info": "[INFO]"}.get(alert.get("severity"), "[ALERT]")
    if source == "bill_mind" and composed:
        return f"Bill (concierge alert) {icon} {stamp}:\n{composed}"
    reason = source.replace("fallback:", "")
    return f"Tower alert {icon} {stamp} (Bill's mind unavailable: {reason}):\n{alert['text']}"


# ── commands ────────────────────────────────────────────────────────────────

def cmd_facts():
    facts = gather_facts()
    print(json.dumps(facts, indent=2, default=str))


def do_briefing(force: bool, dry_run: bool) -> dict:
    state = load_state()
    now = now_epoch()
    last = state.get("last_briefing_epoch", 0)
    if not force and (now - last) < BRIEFING_MIN_INTERVAL:
        wait = int((BRIEFING_MIN_INTERVAL - (now - last)) / 60)
        print(f"briefing skipped: rate-limited ({wait}min until next). Use --force to override.")
        return {"pushed": False, "reason": "rate_limited"}

    facts = gather_facts()
    lines = facts_to_lines(facts)
    facts_text = "\n".join(lines)
    print("=== REAL FACTS GATHERED ===")
    for l in lines:
        print("  " + l)

    # 2026-07-30 (Ross: "he only gets the same questions ... make it real-time, real-live"):
    # rotate the briefing FOCUS from live tower state so each briefing is about a DIFFERENT
    # real thing (health / trading / a real floor / a recent event / what changed), instead
    # of the same "morning briefing" that made every push read identically. Falls back to a
    # generic ask only if the topic generator is unavailable — never blocks the briefing.
    topic = None
    try:
        import qsb_bill_topics as TOPICS
        ask, topic = TOPICS.concierge_ask(facts_text)
    except Exception as e:
        print(f"(topic gen unavailable: {str(e)[:50]} — generic ask)")
        ask = ("give Ross a short, FRESH concierge note on whatever most needs his attention "
               "right now — vary your opener, be specific and new.")
    if topic:
        print(f"=== TOPIC angle={topic['angle']} focus={topic['label']} "
              f"deltas={len(topic['deltas'])} ===")
    composed, source = compose_via_bill(facts_text, ask)
    print(f"\n=== BILL COMPOSE: source={source} ===")
    if composed:
        print("  " + composed)
    else:
        print("  (Bill's mind did not compose — honest fallback to raw auto-summary)")

    # de-dupe: don't push an identical briefing body twice in a row
    msg = build_briefing_message(facts, composed, source)
    body_sig = (composed or facts_text)[:400]
    if not force and state.get("last_briefing_sig") == body_sig:
        print("briefing skipped: identical to last briefing (no change).")
        return {"pushed": False, "reason": "no_change"}

    if dry_run:
        print("\n=== DRY-RUN (not pushed) — would send to Ross: ===")
        print(msg)
        return {"pushed": False, "reason": "dry_run", "message": msg}

    result = push_to_ross(msg)
    print(f"\n=== PUSH TO ROSS: {json.dumps(result)} ===")
    if result.get("ok"):
        state["last_briefing_epoch"] = now
        state["last_briefing_sig"] = body_sig
    state["last_facts"] = facts
    save_state(state)
    log({"event": "briefing", "source": source, "pushed": result.get("ok"),
         "message_id": result.get("message_id"), "channel": result.get("channel"),
         "error": result.get("error")})
    return {"pushed": result.get("ok"), "source": source, "result": result, "message": msg}


def do_alerts(dry_run: bool) -> dict:
    state = load_state()
    facts = gather_facts()
    alerts = compute_alerts(facts, state)
    now = now_epoch()
    cooldowns = state.get("alert_cooldowns", {})
    seen = set(state.get("alert_dedup", [])[-200:])
    fired = []

    for a in alerts:
        ck = a["cooldown_key"]
        dk = a["dedup_key"]
        if dk in seen:
            continue  # already alerted this exact condition
        gap = ALERT_COOLDOWN.get(ck, 30 * 60)
        if now - cooldowns.get(ck, 0) < gap:
            continue  # cooling down on this alert class
        # route through Bill for the wording, honest fallback otherwise
        ask = f"tell Ross this needs his attention: {a['text']} One or two sentences."
        composed, source = compose_via_bill(a["text"], ask, wait_s=45)
        msg = build_alert_message(a, composed, source)
        if dry_run:
            print(f"[DRY alert:{a['kind']}] {msg}")
            fired.append({"kind": a["kind"], "source": source, "pushed": False})
            continue
        result = push_to_ross(msg)
        print(f"[alert:{a['kind']}] source={source} push={json.dumps(result)}")
        if result.get("ok"):
            cooldowns[ck] = now
            seen.add(dk)
            fired.append({"kind": a["kind"], "source": source, "pushed": True,
                          "message_id": result.get("message_id")})
        log({"event": "alert", "kind": a["kind"], "severity": a.get("severity"),
             "source": source, "pushed": result.get("ok"),
             "message_id": result.get("message_id"), "text": a["text"]})

    if not dry_run:
        state["alert_cooldowns"] = cooldowns
        state["alert_dedup"] = list(seen)[-200:]
        state["last_facts"] = facts  # baseline for next diff
        save_state(state)

    if not fired:
        print(f"alerts: no new Ross-worthy events ({len(alerts)} candidate(s), all deduped/cooling).")
    return {"fired": fired, "candidates": len(alerts)}


def main():
    ap = argparse.ArgumentParser(description="Bill's proactive concierge feed.")
    ap.add_argument("--briefing", action="store_true", help="periodic concierge briefing to Ross")
    ap.add_argument("--alerts", action="store_true", help="scan for Ross-worthy events and alert")
    ap.add_argument("--tick", action="store_true", help="alerts + rate-limited briefing (timer target)")
    ap.add_argument("--facts", action="store_true", help="print gathered real facts only")
    ap.add_argument("--force", action="store_true", help="ignore briefing rate-limit")
    ap.add_argument("--dry-run", action="store_true", help="compute + compose but do NOT push to Ross")
    a = ap.parse_args()

    if a.facts:
        cmd_facts(); return
    if a.alerts:
        do_alerts(a.dry_run); return
    if a.briefing:
        do_briefing(a.force, a.dry_run); return
    if a.tick:
        # event alerts first (immediate), then a rate-limited briefing
        do_alerts(a.dry_run)
        do_briefing(force=False, dry_run=a.dry_run)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
