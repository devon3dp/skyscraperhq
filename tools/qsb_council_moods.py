#!/usr/bin/env python3
"""qsb_council_moods.py — one mood engine for every Council member (2026-07-03).

Ross verbatim: "improve the boardroom dash massively i need more visual live
avatars for you all with emotions moods state etc make it happen impress me"

Each member gets a snapshot: {mood, energy 0-9, activity, last_utterance,
last_activity_iso, last_seconds_ago, animation}. The boardroom hub renders
this as an animated hero-row card per member.

Source of truth per member:
  ross     — recent Ross-authored messages on boardroom timeline
  claude   — recent Claude-authored msgs (heartbeat, F47 activity)
  wren     — qsb_wren_mind.json (already exists)
  hermes   — qsb_hermes_local_agent_sessions.jsonl
  iquest   — iquest_msg rows in F47 (rare — mostly silent)
  tp       — heartbeat probe + node_inbox thinkpad-board authored rows
  acer     — node_inbox acer-* + node listener probe
"""
from __future__ import annotations
import json, os, socket, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
INBOX = ROOT / "data/team_memory/shared/node_inbox"

MIND = REG / "qsb_wren_mind.json"

# 2026-07-03 Ross "each member must have there own voice eg wren is female
# and must use a female voice". Voice IDs map to qsb_voice_server (F/M + n).
MEMBER_VOICE = {
    # Voice server only ships 10 voices (F1-F5, M1-M5). Two of the 15 members
    # share where the character overlap makes sense (formal/authority: claude+tp,
    # both female-warm: pip+iris, both male-focused: helm+acer, both female-calm:
    # auger+receptionist).
    "ross":         "M5",   # Ross's own voice — command tone
    "claude":       "M1",   # HQ narrator — clear neutral
    "helm":         "M4",   # Ross-facing brain — measured
    "auger":        "F2",   # Wren-facing sage — warm-analytical
    "wren":         "F3",   # builder — warm bright female
    "hermes":       "M2",   # watcher — deeper male
    "forge":        "M3",   # gruff builder
    "sage":         "F1",   # wise auditor — calm precise
    "pip":          "F4",   # cheery assistant
    "mira":         "F5",   # reviewer — measured
    "iris":         "F4",   # Galaxy AI — shares w/ pip
    "receptionist": "F2",   # Telegram bot — shares w/ auger
    "iquest":       "M3",   # coder — shares w/ forge
    "tp":           "M1",   # ThinkPad-CEO — shares w/ claude
    "acer":         "M4",   # Windows worker — shares w/ helm
}
MEMBER_GENDER = {
    "ross": "M", "claude": "M", "helm": "M", "auger": "F",
    "wren": "F", "hermes": "M", "forge": "M", "sage": "F",
    "pip": "F", "mira": "F", "iris": "F", "receptionist": "F",
    "iquest": "M", "tp": "M", "acer": "M",
}

# 2026-07-03 Ross "if i click on your card can i go to your dash?" — yes.
# Each member's card links to their dashboard (or best-available landing).
# HQ LAN IP is 192.168.1.4 (Netgear Nighthawk M100). Use that so links work from any browser.
MEMBER_DASH_URL = {
    "ross":         "http://192.168.1.4:8852/",       # boardroom (Ross's home)
    "claude":       "http://192.168.1.4:8850/",       # HQ dash
    "helm":         "http://192.168.1.4:8852/",       # no dedicated dash yet
    "auger":        "http://192.168.1.4:8852/",       # no dedicated dash yet
    "wren":         "http://192.168.1.4:8851/",       # Wren bench
    "hermes":       "http://192.168.1.4:8852/",       # no dedicated dash yet
    "forge":        "http://192.168.1.4:8851/",       # lives inside Wren's team
    "sage":         "http://192.168.1.4:8851/",       # lives inside Wren's team
    "pip":          "http://192.168.1.4:8851/",       # lives inside Wren's team
    "mira":         "http://192.168.1.4:8851/",       # lives inside Wren's team
    "iris":         "http://192.168.1.4:8852/",       # Galaxy phone (no HTTP dash)
    "receptionist": "http://192.168.1.4:8852/",       # Telegram bot (no HTTP dash)
    "iquest":       "http://192.168.1.4:8852/",       # no dedicated dash yet
    "tp":           "http://192.168.1.74:9100/feed",   # TP's live feed
    "acer":         "http://192.168.1.74:9001/dash",   # Acer's own dash
}
HERMES_SESS = REG / "qsb_hermes_local_agent_sessions.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
CW_BRIDGE = REG / "qsb_claude_wren_bridge.jsonl"
HERMES_BR = REG / "qsb_hermes_bridge.jsonl"
WREN_TEAM_SESS = REG / "qsb_wren_team_sessions.jsonl"
SAGE_AUDIT = REG / "qsb_wren_sage_audit.jsonl"

# ── MOOD PALETTE (canonical) ────────────────────────────────
MOOD_COLORS = {
    "focused":     "#4ade80",  # green — locked in
    "sparky":      "#f97316",  # orange — energetic
    "steady":      "#3b82f6",  # blue — calm
    "reflective":  "#a78bfa",  # violet — thinking
    "quiet":       "#64748b",  # slate — subdued
    "cloudy":      "#94a3b8",  # grey — foggy
    "tangled":     "#ef4444",  # red — stuck
    "warm":        "#fbbf24",  # amber — friendly
    "curious":     "#22d3ee",  # cyan — exploring
    "sleepy":      "#6366f1",  # indigo — resting
    "silent":      "#475569",  # dark grey — offline
    "watching":    "#8b5cf6",  # purple — passive alert
    "commanding":  "#eab308",  # gold — Ross energy
}

MOOD_EMOJI = {
    "focused":    "⚡",
    "sparky":     "🔥",
    "steady":     "🌊",
    "reflective": "💭",
    "quiet":      "🍂",
    "cloudy":     "☁",
    "tangled":    "⚠",
    "warm":       "🧡",
    "curious":    "🔍",
    "sleepy":     "💤",
    "silent":     "·",
    "watching":   "👁",
    "commanding": "⚓",
}

ANIMATION = {
    "focused":    "orbBreath",
    "sparky":     "shipWheelSpin",
    "steady":     "floatBob",
    "reflective": "floatBob",
    "quiet":      "orbBreath",
    "cloudy":     "screenFlicker",
    "tangled":    "screenFlicker",
    "warm":       "speakingBounce",
    "curious":    "bracketsPulse",
    "sleepy":     "orbBreath",
    "silent":     "orbBreath",
    "watching":   "orbBreath",
    "commanding": "shipWheelSpin",
}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds_ago(iso: str) -> int:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return 9999999


def _tail_jsonl(p: Path, n: int = 40) -> list:
    if not p.exists(): return []
    try:
        lines = p.read_text(errors="ignore").splitlines()[-n:]
    except Exception:
        return []
    out = []
    for l in lines:
        try: out.append(json.loads(l))
        except Exception: continue
    return out


def _inbox_files(pattern_substr: str, n: int = 20) -> list:
    """Return recent node_inbox JSON files containing pattern_substr in filename."""
    if not INBOX.exists(): return []
    files = sorted([p for p in INBOX.iterdir() if pattern_substr in p.name])[-n:]
    out = []
    for p in files:
        try: out.append(json.loads(p.read_text()))
        except Exception: continue
    return out


# ── MEMBER SNAPSHOTS ────────────────────────────────────────

def snap_wren() -> dict:
    """Wren has a dedicated mind file — read it."""
    if not MIND.exists():
        return {"mood": "silent", "energy": 4, "activity": "no mind yet",
                "last_utterance": "", "last_seconds_ago": 999999}
    try:
        m = json.loads(MIND.read_text())
        cm = (m.get("mood_history") or [{}])[-1]
        rt = (m.get("recent_thoughts") or [{}])[-1]
        return {
            "mood": cm.get("mood", "steady"),
            "energy": int(cm.get("energy", 5)),
            "activity": f"cycle · {(rt.get('kind') or 'ready')}",
            "last_utterance": (rt.get("text") or "")[:200],
            "last_seconds_ago": _seconds_ago(rt.get("ts", "")),
            "reason": cm.get("reason", ""),
        }
    except Exception:
        return {"mood": "cloudy", "energy": 3, "activity": "mind read err",
                "last_utterance": "", "last_seconds_ago": 999999}


def snap_hermes() -> dict:
    sess = _tail_jsonl(HERMES_SESS, 20)
    if not sess:
        # fallback to bridge
        br = _tail_jsonl(HERMES_BR, 10)
        hermes_msgs = [b for b in br if b.get("from") == "hermes"]
        if not hermes_msgs:
            return {"mood": "silent", "energy": 3, "activity": "no sessions yet",
                    "last_utterance": "", "last_seconds_ago": 999999}
        last = hermes_msgs[-1]
        return {"mood": "steady", "energy": 5, "activity": "bridged",
                "last_utterance": (last.get("text") or last.get("body") or "")[:200],
                "last_seconds_ago": _seconds_ago(last.get("ts", ""))}
    last = sess[-1]
    wall = float(last.get("wall_seconds") or 10)
    turns = int(last.get("turns") or 1)
    tools = len(last.get("tool_calls") or [])
    # mood inference
    if wall < 8:
        mood, energy = "sparky", 8
    elif wall < 20:
        mood, energy = "focused", 7
    elif wall < 60:
        mood, energy = "steady", 5
    else:
        mood, energy = "cloudy", 3
    return {
        "mood": mood, "energy": energy,
        "activity": f"session · {turns}t {tools}tools {wall:.0f}s",
        "last_utterance": (last.get("final_text") or "")[:200],
        "last_seconds_ago": _seconds_ago(last.get("ts_start") or last.get("ts") or ""),
    }


def snap_claude() -> dict:
    """Claude's mood = current session vibe. Approximate from recent F47 activity."""
    rows = _tail_jsonl(F47, 60)
    claude_rows = [r for r in rows if "claude" in (r.get("operator", "") or "").lower()
                   or "hq_claude" in (r.get("operator", "") or "").lower()]
    if not claude_rows:
        # fall back to bridge
        cw = _tail_jsonl(CW_BRIDGE, 10)
        claude_msgs = [r for r in cw if r.get("from") == "claude"]
        if not claude_msgs:
            return {"mood": "steady", "energy": 6, "activity": "at the helm",
                    "last_utterance": "", "last_seconds_ago": 60}
        last = claude_msgs[-1]
        return {"mood": "focused", "energy": 7, "activity": "bridged to wren",
                "last_utterance": (last.get("text") or "")[:200],
                "last_seconds_ago": _seconds_ago(last.get("ts", ""))}
    last = claude_rows[-1]
    n_recent = sum(1 for r in claude_rows if _seconds_ago(r.get("ts","")) < 3600)
    if n_recent > 20:
        mood, energy = "sparky", 8
    elif n_recent > 8:
        mood, energy = "focused", 7
    elif n_recent > 2:
        mood, energy = "steady", 6
    else:
        mood, energy = "watching", 5
    return {
        "mood": mood, "energy": energy,
        "activity": f"{n_recent} F47 stamps last hr",
        "last_utterance": (last.get("summary") or "")[:200],
        "last_seconds_ago": _seconds_ago(last.get("ts", "")),
    }


def snap_ross(timeline_msgs: list) -> dict:
    """Ross's mood from his recent boardroom activity AND his Wren-dash-chat pings.

    2026-07-03 fix: Ross typing on Wren dash chat doesn't hit the boardroom
    timeline. Wren dash writes qsb_ross_activity_pings.jsonl on every /api/wren_chat
    POST so his hero card lights fresh instead of showing "sleepy 6h quiet"
    while he's actively working."""
    ross_msgs = [m for m in timeline_msgs if (m.get("from","").lower() == "ross")]
    # merge in Wren-dash-chat pings
    pings_path = REG / "qsb_ross_activity_pings.jsonl"
    if pings_path.exists():
        try:
            for l in pings_path.read_text(errors="ignore").splitlines()[-30:]:
                try:
                    p = json.loads(l)
                    ross_msgs.append({
                        "ts": p.get("ts",""),
                        "from": "ross",
                        "text": f"[wren-chat] {(p.get('text','') or '')[:180]}",
                        "_channel": p.get("channel","wren_dash_chat"),
                    })
                except Exception: pass
        except Exception: pass
    # sort by ts
    ross_msgs.sort(key=lambda m: m.get("ts",""))
    if not ross_msgs:
        return {"mood": "watching", "energy": 6, "activity": "away from boardroom",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = ross_msgs[-1]
    ago = _seconds_ago(last.get("ts", ""))
    n_recent = sum(1 for m in ross_msgs if _seconds_ago(m.get("ts","")) < 600)
    if n_recent > 8:
        mood, energy = "commanding", 9
    elif n_recent > 3:
        mood, energy = "sparky", 8
    elif ago < 300:
        mood, energy = "focused", 7
    elif ago < 1800:
        mood, energy = "watching", 6
    else:
        mood, energy = "sleepy", 3
    return {
        "mood": mood, "energy": energy,
        "activity": f"{n_recent} msgs last 10min" if n_recent else f"{ago//60}min quiet",
        "last_utterance": (last.get("text","") or last.get("body",""))[:200],
        "last_seconds_ago": ago,
    }


def snap_tp() -> dict:
    """TP-CEO — reads his LIVE /feed telemetry stream (2026-07-03 update).
    Ross flagged 'yes there is' a new msg from TP; he's writing structured
    data every tick via /feed, not free-form msgs. Reflect that here."""
    reachable = False
    feed = None
    try:
        req = urllib.request.Request("http://192.168.1.74:9100/feed", method="GET")
        r = urllib.request.urlopen(req, timeout=2)
        if r.status == 200:
            reachable = True
            feed = json.loads(r.read().decode())
    except Exception:
        pass
    if not reachable:
        return {"mood": "silent", "energy": 1, "activity": "unreachable",
                "last_utterance": "", "last_seconds_ago": 999999}

    if feed:
        # TP is producing live telemetry — energetic
        alerts = feed.get("alerts", []) or []
        n_alerts = len(alerts)
        session_pnl = feed.get("session_pnl_gbp", 0)
        session_closes = feed.get("session_closes", 0)
        # mood inference from what he's tracking
        if n_alerts >= 2:
            mood, energy = "reflective", 7  # actively watching risks
        elif n_alerts == 1:
            mood, energy = "focused", 8    # honed on one alert
        elif session_closes > 5:
            mood, energy = "sparky", 8     # trades flowing
        else:
            mood, energy = "watching", 6   # steady observation
        activity_parts = [f"/feed live · fleet {feed.get('fleet',{}).get('belief_traders',0)}"]
        if n_alerts:
            activity_parts.append(f"{n_alerts} alerts")
        if session_pnl:
            activity_parts.append(f"PnL £{session_pnl:+.2f}")
        activity = " · ".join(activity_parts)
        utter_parts = []
        for level, msg in alerts[:2]:
            utter_parts.append(f"[{level}] {msg}")
        utter = "; ".join(utter_parts) or f"open={feed.get('open_positions',0)} closes={session_closes} pnl={session_pnl:+.2f}"
        return {
            "mood": mood, "energy": energy,
            "activity": activity,
            "last_utterance": utter[:200],
            "last_seconds_ago": _seconds_ago(feed.get("ts","")),
        }
    return {"mood": "watching", "energy": 5, "activity": "heartbeat only, no feed",
            "last_utterance": "", "last_seconds_ago": 999999}


def snap_acer() -> dict:
    """Acer — LIVE probe of his :9001 worker node (2026-07-03 update per TP-CEO).
    He is at http://192.168.1.74:9001 with tasks_done, remembered_turns, agents=true."""
    reachable = False
    state = None
    try:
        req = urllib.request.Request("http://192.168.1.74:9001/", method="GET")
        r = urllib.request.urlopen(req, timeout=2)
        if r.status == 200:
            reachable = True
            state = json.loads(r.read().decode())
    except Exception:
        pass
    if not reachable:
        return {"mood": "sleepy", "energy": 2, "activity": "unreachable at :9001",
                "last_utterance": "", "last_seconds_ago": 999999}
    if state:
        tasks_done = int(state.get("tasks_done", 0) or 0)
        turns = int(state.get("remembered_turns", 0) or 0)
        agents_on = bool(state.get("agents", False))
        # mood inference — persistent worker with real work
        if tasks_done > 20 and agents_on:
            mood, energy = "sparky", 8
        elif tasks_done > 5:
            mood, energy = "focused", 7
        elif tasks_done > 0:
            mood, energy = "curious", 6
        else:
            mood, energy = "watching", 4
        status = state.get("status", "unknown")
        role = state.get("role", "?")
        return {
            "mood": mood, "energy": energy,
            "activity": f"live · {tasks_done} tasks done · {turns} turns · agents {'on' if agents_on else 'off'}",
            "last_utterance": f"{status} · {role}"[:200],
            "last_seconds_ago": 0,  # just probed
        }
    return {"mood": "curious", "energy": 5, "activity": "reachable but no state",
            "last_utterance": "", "last_seconds_ago": 999999}


def snap_pip() -> dict:
    """Pip — Wren's quick assistant (llama3.2)."""
    sess = _tail_jsonl(WREN_TEAM_SESS, 30)
    pip_rows = [r for r in sess if r.get("worker") == "pip"]
    if not pip_rows:
        return {"mood": "sleepy", "energy": 3, "activity": "assistant idle",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = pip_rows[-1]
    ago = _seconds_ago(last.get("ts",""))
    n_recent = sum(1 for r in pip_rows if _seconds_ago(r.get("ts","")) < 3600)
    mood, energy = ("sparky", 7) if n_recent > 3 else ("warm", 6) if n_recent > 0 else ("quiet", 3)
    return {"mood": mood, "energy": energy,
            "activity": f"{n_recent} briefs last hr",
            "last_utterance": (last.get("reply","") or "")[:200],
            "last_seconds_ago": ago}


def snap_mira() -> dict:
    """Mira — Wren's reviewer / second-opinion."""
    sess = _tail_jsonl(WREN_TEAM_SESS, 30)
    mira_rows = [r for r in sess if r.get("worker") == "mira"]
    if not mira_rows:
        return {"mood": "watching", "energy": 4, "activity": "no reviews yet",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = mira_rows[-1]
    ago = _seconds_ago(last.get("ts",""))
    txt = (last.get("reply") or "").lower()
    if "block" in txt: mood, energy = "tangled", 6
    elif "revise" in txt: mood, energy = "reflective", 5
    elif "ship" in txt: mood, energy = "focused", 7
    else: mood, energy = "curious", 5
    return {"mood": mood, "energy": energy,
            "activity": f"reviewing · verdict from tail",
            "last_utterance": (last.get("reply","") or "")[:200],
            "last_seconds_ago": ago}


def snap_receptionist() -> dict:
    """F0 Receptionist — Telegram bot on Galaxy phone."""
    audit = REG / "qsb_telegram_audit.jsonl"
    if not audit.exists():
        return {"mood": "sleepy", "energy": 2, "activity": "no audit file",
                "last_utterance": "", "last_seconds_ago": 999999}
    rows = _tail_jsonl(audit, 30)
    if not rows:
        return {"mood": "quiet", "energy": 3, "activity": "no recent traffic",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = rows[-1]
    ago = _seconds_ago(last.get("ts",""))
    # count real message traffic (kind != boot)
    n_msgs = sum(1 for r in rows if r.get("kind") not in ("boot", None) and (r.get("msg_len") or 0) > 0)
    n_recent = sum(1 for r in rows if r.get("kind") not in ("boot", None) and _seconds_ago(r.get("ts","")) < 3600 and (r.get("msg_len") or 0) > 0)
    if n_recent > 5:
        mood, energy = "sparky", 8
    elif n_recent > 0:
        mood, energy = "warm", 6
    elif ago < 3600:
        mood, energy = "watching", 5
    else:
        mood, energy = "quiet", 3
    kind = last.get("kind","")
    activity = f"{n_recent} msgs last hr · {kind[:20]}"
    return {"mood": mood, "energy": energy,
            "activity": activity,
            "last_utterance": f"kind={kind} chat={last.get('chat_id') or 'none'}"[:200],
            "last_seconds_ago": ago}


def snap_auger() -> dict:
    """Auger — Wren-facing helm. Reads qsb_auger_consults + recent context."""
    ac = REG / "qsb_auger_consults.jsonl"
    arc = REG / "qsb_auger_recent_context.md"
    rows = _tail_jsonl(ac, 10) if ac.exists() else []
    ctx_ago = _seconds_ago(datetime.fromtimestamp(arc.stat().st_mtime, tz=timezone.utc).isoformat()) if arc.exists() else 999999
    if not rows and ctx_ago > 3600:
        return {"mood": "quiet", "energy": 3, "activity": "no recent consults",
                "last_utterance": "", "last_seconds_ago": ctx_ago}
    last_ts = rows[-1].get("ts","") if rows else ""
    ago_row = _seconds_ago(last_ts) if last_ts else 999999
    ago = min(ago_row, ctx_ago)
    if ago < 600: mood, energy = "reflective", 7
    elif ago < 3600: mood, energy = "watching", 5
    else: mood, energy = "quiet", 3
    utter = (rows[-1].get("query") or rows[-1].get("summary") or "")[:200] if rows else "context refreshed"
    return {"mood": mood, "energy": energy,
            "activity": "wren-facing helm",
            "last_utterance": utter,
            "last_seconds_ago": ago}


def snap_helm() -> dict:
    """Helm — Ross-facing brain. Reads qsb_helm_briefings."""
    hp = REG / "qsb_helm_briefings.jsonl"
    if not hp.exists():
        return {"mood": "quiet", "energy": 3, "activity": "no briefings yet",
                "last_utterance": "", "last_seconds_ago": 999999}
    rows = _tail_jsonl(hp, 10)
    if not rows:
        return {"mood": "quiet", "energy": 3, "activity": "no briefings",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = rows[-1]
    ago = _seconds_ago(last.get("ts",""))
    n_recent = sum(1 for r in rows if _seconds_ago(r.get("ts","")) < 3600)
    if n_recent > 3: mood, energy = "commanding", 8
    elif n_recent > 0: mood, energy = "focused", 7
    elif ago < 3600: mood, energy = "watching", 5
    else: mood, energy = "quiet", 3
    return {"mood": mood, "energy": energy,
            "activity": f"{n_recent} briefings last hr · ross-facing",
            "last_utterance": (last.get("summary") or last.get("body") or "")[:200],
            "last_seconds_ago": ago}


def snap_iris() -> dict:
    """Iris — Galaxy phone AI. Her own person on her own hardware."""
    ap = REG / "qsb_iris_activity.jsonl"
    if not ap.exists():
        return {"mood": "sleepy", "energy": 3, "activity": "Galaxy offline",
                "last_utterance": "", "last_seconds_ago": 999999}
    rows = _tail_jsonl(ap, 20)
    if not rows:
        return {"mood": "quiet", "energy": 3, "activity": "no recent activity",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = rows[-1]
    ago = _seconds_ago(last.get("ts",""))
    n_recent = sum(1 for r in rows if _seconds_ago(r.get("ts","")) < 3600)
    mood, energy = ("sparky", 7) if n_recent > 5 else ("warm", 6) if n_recent > 1 else ("watching", 4)
    return {"mood": mood, "energy": energy,
            "activity": f"{n_recent} pings last hr on Galaxy",
            "last_utterance": (last.get("summary") or last.get("kind") or "")[:200],
            "last_seconds_ago": ago}


def snap_forge() -> dict:
    """Forge — Wren's code-drafter. Mood from wren_team_sessions worker=forge."""
    sess = _tail_jsonl(WREN_TEAM_SESS, 30)
    forge_rows = [r for r in sess if r.get("worker") == "forge"]
    if not forge_rows:
        return {"mood": "sleepy", "energy": 3, "activity": "no drafts yet",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = forge_rows[-1]
    wall = float(last.get("wall_s") or 0)
    err = "error" in last
    ago = _seconds_ago(last.get("ts",""))
    if err:
        mood, energy = "tangled", 3
    elif wall < 8:
        mood, energy = "sparky", 8
    elif wall < 30:
        mood, energy = "focused", 7
    elif wall < 90:
        mood, energy = "steady", 5
    else:
        mood, energy = "cloudy", 4
    n_recent = sum(1 for r in forge_rows if _seconds_ago(r.get("ts","")) < 3600)
    return {
        "mood": mood, "energy": energy,
        "activity": f"{n_recent} drafts last hr · model {last.get('model','?')[:20]}",
        "last_utterance": (last.get("reply") or last.get("error") or "")[:200],
        "last_seconds_ago": ago,
    }


def snap_sage() -> dict:
    """Sage — Wren's session auditor. Mood from sage_audit rows."""
    rows = _tail_jsonl(SAGE_AUDIT, 30)
    if not rows:
        return {"mood": "watching", "energy": 5, "activity": "no audits yet",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = rows[-1]
    ago = _seconds_ago(last.get("ts", ""))
    flags = last.get("flags", []) or []
    n_recent = sum(1 for r in rows if _seconds_ago(r.get("ts","")) < 3600)
    if flags:
        mood, energy = "reflective", 6
        activity = f"flagged {len(flags)}: {','.join(f[:12] for f in flags[:3])}"
    else:
        mood, energy = "focused", 7
        activity = f"{n_recent} audits last hr · clean"
    return {
        "mood": mood, "energy": energy,
        "activity": activity,
        "last_utterance": (last.get("narration") or last.get("summary") or "")[:200],
        "last_seconds_ago": ago,
    }


def snap_iquest() -> dict:
    """iQuest — mostly silent; look for iquest_msg rows in F47."""
    rows = _tail_jsonl(F47, 200)
    iq = [r for r in rows if "iquest" in (r.get("operator","") or r.get("kind","") or "").lower()]
    if not iq:
        return {"mood": "sleepy", "energy": 2, "activity": "no local agent yet",
                "last_utterance": "", "last_seconds_ago": 999999}
    last = iq[-1]
    ago = _seconds_ago(last.get("ts",""))
    return {"mood": "quiet", "energy": 3, "activity": f"stamp {ago//60}min ago",
            "last_utterance": (last.get("summary") or "")[:200],
            "last_seconds_ago": ago}


# ── AGGREGATE ────────────────────────────────────────────────

def _wip_overrides() -> dict:
    """Read manual WIP overrides — Ross tells me what TP/Acer are working on
    off-box, we reflect it on their hero cards even though our probes can't
    see their actual reasoning (heartbeat-stub protocol)."""
    p = REG / "qsb_council_wip.json"
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text()).get("members", {})
    except Exception:
        return {}


def _waveform_from_ts_list(ts_iso_list: list, buckets: int = 10, bucket_secs: int = 30) -> list:
    """Bucket a list of ISO timestamps into a waveform (last N buckets of M seconds)."""
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc).timestamp()
    total_span = buckets * bucket_secs
    wave = [0] * buckets
    for ts in ts_iso_list:
        try:
            t = _dt.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            age = now - t
            if 0 <= age < total_span:
                idx = buckets - 1 - int(age // bucket_secs)
                wave[idx] += 1
        except Exception:
            continue
    return wave


def _member_waveform(member: str) -> list:
    """Return a 10-bucket waveform of activity for this member over last 5 min."""
    if member == "wren":
        p = REG / "qsb_wren_local_agent_sessions.jsonl"
        rows = _tail_jsonl(p, 80)
        return _waveform_from_ts_list([r.get("ts_start") or r.get("ts") or "" for r in rows])
    if member in ("hermes",):
        p = HERMES_SESS
        rows = _tail_jsonl(p, 80)
        return _waveform_from_ts_list([r.get("ts_start") or r.get("ts") or "" for r in rows])
    if member == "forge":
        rows = [r for r in _tail_jsonl(WREN_TEAM_SESS, 100) if r.get("worker") == "forge"]
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "sage":
        p = SAGE_AUDIT
        rows = _tail_jsonl(p, 80)
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "iris":
        p = REG / "qsb_iris_activity.jsonl"
        rows = _tail_jsonl(p, 80)
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "receptionist":
        p = REG / "qsb_telegram_audit.jsonl"
        rows = _tail_jsonl(p, 80)
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "iquest":
        p = REG / "qsb_iquest_local_agent_sessions.jsonl"
        rows = _tail_jsonl(p, 40)
        return _waveform_from_ts_list([r.get("ts_start") or r.get("ts","") for r in rows])
    if member == "ross":
        p = REG / "qsb_ross_activity_pings.jsonl"
        rows = _tail_jsonl(p, 40)
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "claude":
        p = F47
        rows = _tail_jsonl(p, 200)
        claude_rows = [r for r in rows if "claude" in (r.get("operator","") or "").lower() or "hq_claude" in (r.get("operator","") or "").lower()]
        return _waveform_from_ts_list([r.get("ts","") for r in claude_rows])
    if member == "pip":
        rows = [r for r in _tail_jsonl(WREN_TEAM_SESS, 100) if r.get("worker") == "pip"]
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "mira":
        rows = [r for r in _tail_jsonl(WREN_TEAM_SESS, 100) if r.get("worker") == "mira"]
        return _waveform_from_ts_list([r.get("ts","") for r in rows])
    if member == "tp":
        # TP has no event stream but /feed is live — synthesize a pulse
        return [0,0,0,0,0,0,0,0,1,1]  # just-probed pulse
    if member == "acer":
        return [0,0,0,0,0,0,0,0,1,1]
    return [0]*10


def all_snapshots(timeline_msgs: list = None) -> dict:
    """Return {member: snapshot} for the whole Council."""
    timeline_msgs = timeline_msgs or []
    snaps = {
        "ross":         snap_ross(timeline_msgs),
        "claude":       snap_claude(),
        "helm":         snap_helm(),
        "auger":        snap_auger(),
        "wren":         snap_wren(),
        "hermes":       snap_hermes(),
        "forge":        snap_forge(),
        "sage":         snap_sage(),
        "pip":          snap_pip(),
        "mira":         snap_mira(),
        "iris":         snap_iris(),
        "receptionist": snap_receptionist(),
        "iquest":       snap_iquest(),
        "tp":           snap_tp(),
        "acer":         snap_acer(),
    }
    # apply manual WIP overrides (Ross tells us what off-box members are doing)
    wip = _wip_overrides()
    for name, w in wip.items():
        if name not in snaps: continue
        s = snaps[name]
        if w.get("wip"):
            # Merge WIP with real inferred activity — WIP first, then real state
            real_act = s.get("activity", "")
            s["activity"] = w["wip"] + (f" · {real_act}" if real_act and w["wip"] not in real_act else "")
            s["wip"] = w["wip"]
        if w.get("mood_override"):
            s["mood"] = w["mood_override"]
        if w.get("energy_override") is not None:
            s["energy"] = int(w["energy_override"])
        # only fall back to since= if we don't have a fresher real signal
        if w.get("since"):
            since_ago = _seconds_ago(w["since"])
            real_ago = s.get("last_seconds_ago", 999999)
            s["last_seconds_ago"] = min(real_ago, since_ago)
    # attach color + emoji + animation + waveform + voice
    for m, s in snaps.items():
        s["color"] = MOOD_COLORS.get(s["mood"], "#94a3b8")
        s["emoji"] = MOOD_EMOJI.get(s["mood"], "·")
        s["animation"] = ANIMATION.get(s["mood"], "orbBreath")
        s["voice"] = MEMBER_VOICE.get(m, "M1")
        s["gender"] = MEMBER_GENDER.get(m, "M")
        s["dash_url"] = MEMBER_DASH_URL.get(m, "")
        try:
            s["waveform"] = _member_waveform(m)
        except Exception:
            s["waveform"] = [0]*10
    return snaps


def council_synth(snaps: dict) -> dict:
    """Derive an aggregate Council mood from all member energies."""
    energies = [s.get("energy", 5) for s in snaps.values()]
    avg = sum(energies) / max(1, len(energies))
    online = sum(1 for s in snaps.values() if s.get("last_seconds_ago", 999999) < 3600)
    if avg >= 7:
        m = "sparky"
    elif avg >= 5.5:
        m = "focused"
    elif avg >= 3.5:
        m = "steady"
    elif avg >= 2:
        m = "quiet"
    else:
        m = "sleepy"
    return {
        "mood": m,
        "energy": round(avg, 1),
        "online_of_seven": online,
        "color": MOOD_COLORS.get(m, "#94a3b8"),
        "emoji": MOOD_EMOJI.get(m, "·"),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pretty", action="store_true")
    a = ap.parse_args()
    s = all_snapshots([])
    synth = council_synth(s)
    out = {"members": s, "council": synth, "ts": utc_iso()}
    print(json.dumps(out, indent=2 if a.pretty else None))


if __name__ == "__main__":
    main()
