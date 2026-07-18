#!/usr/bin/env python3
"""wren self-portrait dashboard — designed by wren, 2026-07-02.

Ross 2026-07-02: "now using our local agents get wren to build her page prove
it lets see what she designs for us all and esp me so i can see her let her
do it".

Design decisions came from Wren via qsb_wren_local_agent (session wsess_ad12ca,
qwen3.5:9b, 7.2s):
  avatar:  rotating engineer's wrench with brass handle
  palette: primary=#3b82f6  glow=#f97316  background=#0f172a
  traits:  warmth=8 precision=9 speed=8 curiosity=7 patience=8
  layout:  grid-tile-mosaic
  tagline: "Building floors, shipping code, keeping Ross informed every day."
  distinct panel: live floor-cards shipped today

HQ-Claude coded the file to Wren's spec. Port 8851 (mine's on 8850).
"""
from __future__ import annotations
import argparse, json, os, socket, subprocess, sys, time
import urllib.request, urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VOICE_ENDPOINT = "http://127.0.0.1:8795"  # qsb_voice_server (POST /tts, /stt)
WREN_AGENT = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_wren_local_agent.py")
CHAT_LOG = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_wren_dash_chat.jsonl")

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
WREN_SESS = ROOT / "data/registries/qsb_wren_local_agent_sessions.jsonl"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
FLOORS_DIR = ROOT / "floors"
MEMORY_DIR = Path("/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory")
GATE = ROOT / "data/registries/qsb_wren_local_agentic_gate.json"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tail_jsonl(p: Path, k: int):
    if not p.exists():
        return []
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 800_000))
            chunk = f.read().decode("utf-8", errors="ignore")
        lines = [l for l in chunk.splitlines() if l.strip()]
        rows = []
        for l in lines[::-1]:
            try:
                rows.append(json.loads(l))
            except Exception:
                continue
            if len(rows) >= k:
                break
        return rows
    except Exception:
        return []


def identity():
    return {
        "name": "Wren",
        "model": "qwen3.5:9b",
        "family": "qwen35",
        "provider": "Ollama · local",
        "floor": "F46 · Wren Bench",
        "role": "builder-engineer partner",
        "helix": "F47 mutual review with Claude",
        "tagline": "Building floors, shipping code, keeping Ross informed every day.",
    }


def traits():
    # Wren's own values from her design spec 2026-07-02
    return {
        "warmth": 8,
        "precision": 9,
        "speed": 8,
        "curiosity": 7,
        "patience": 8,
    }


def toolbelt():
    gate = {}
    if GATE.exists():
        try: gate = json.loads(GATE.read_text())
        except Exception: pass
    tools = gate.get("tools", {})
    def s(name, hue, icon):
        cfg = tools.get(name, {})
        mode = cfg.get("mode", "direct" if cfg.get("enabled", True) else "off")
        return {"name": name.replace("wren_", ""), "hue": hue, "icon": icon,
                "enabled": cfg.get("enabled", True), "mode": mode}
    return [
        s("wren_read_file",         210, "📖"),
        s("wren_grep_repo",         200, "🔎"),
        s("wren_retrieve",          220, "◈"),
        s("wren_edit_file",         30,  "✏️"),
        s("wren_bash",              300, "⌘"),
        s("wren_scrcpy",            280, "📱"),
        s("wren_curl",              200, "🌐"),
        s("wren_stamp_f47_record",  120, "✔"),
        s("wren_propose_patch",     30,  "◆"),
        s("wren_list_skills",       160, "◇"),
        s("wren_run_skill",         160, "▶"),
        s("wren_message_claude",    30,  "✉"),
    ]


def sessions_stats():
    rows = _tail_jsonl(WREN_SESS, 200)
    if not rows:
        return {"count_total_est": 0, "recent_shown": 0, "avg_wall_s": None,
                "avg_tool_calls": None, "most_used_tool": None, "recent": []}
    total = 0
    try:
        with WREN_SESS.open("rb") as f:
            for _ in f:
                total += 1
    except Exception:
        total = len(rows)
    wall = [r.get("wall_seconds", 0) for r in rows if r.get("wall_seconds")]
    tool_ns = [len(r.get("tool_calls", [])) for r in rows]
    fn_hits = {}
    for r in rows:
        for tc in r.get("tool_calls", []):
            fn_hits[tc.get("fn", "")] = fn_hits.get(tc.get("fn", ""), 0) + 1
    most = max(fn_hits.items(), key=lambda kv: kv[1])[0] if fn_hits else None
    recent = []
    for r in rows[:8]:
        recent.append({
            "sid": (r.get("session_id") or "")[:12],
            "ts": (r.get("ts_start") or "")[:19],
            "model": r.get("model", ""),
            "turns": r.get("turns", 0),
            "tools": len(r.get("tool_calls", [])),
            "wall_s": r.get("wall_seconds", 0),
            "final_head": (r.get("final_text") or "")[:180],
        })
    return {
        "count_total_est": total,
        "recent_shown": len(rows),
        "avg_wall_s": round(sum(wall) / len(wall), 2) if wall else None,
        "avg_tool_calls": round(sum(tool_ns) / len(tool_ns), 2) if tool_ns else None,
        "most_used_tool": most,
        "recent": recent,
    }


def last_wren_final_text():
    rows = _tail_jsonl(WREN_SESS, 50)
    for r in rows:
        t = (r.get("final_text") or "").strip()
        if t:
            return {"text": t[:400], "ts": (r.get("ts_end") or "")[:19]}
    return {"text": "", "ts": ""}


def wren_f47_stamps(n=12):
    rows = _tail_jsonl(F47, 500)
    out = []
    for r in rows:
        blob = json.dumps(r).lower()
        if "wren" in blob:
            out.append({
                "ts": (r.get("ts") or "")[:19],
                "kind": (r.get("kind") or r.get("event_kind") or "")[:40],
                "subject": (r.get("subject") or "")[:110],
            })
            if len(out) >= n:
                break
    return out


def floor_cards_today():
    """Wren's requested distinct panel — floor cards shipped today."""
    today = utc_iso()[:10]
    out = []
    try:
        for cardp in sorted(FLOORS_DIR.glob("*/floor_card.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True):
            mtime = datetime.utcfromtimestamp(cardp.stat().st_mtime).isoformat()
            if mtime[:10] == today:
                try:
                    d = json.loads(cardp.read_text())
                except Exception:
                    d = {}
                out.append({
                    "floor": cardp.parent.name,
                    "name": d.get("floor_name", d.get("name", "")),
                    "owner": d.get("owner", ""),
                    "mtime": mtime[:19],
                })
            if len(out) >= 12:
                break
    except Exception:
        pass
    return out


def wren_memory_pulses(n=8):
    """Memory files that mention Wren (by name), sorted by mtime."""
    hits = []
    try:
        for f in MEMORY_DIR.glob("*.md"):
            try:
                head = f.read_text(errors="ignore")[:4000]
            except Exception:
                continue
            if "wren" in head.lower():
                hits.append((f.stat().st_mtime, f))
        hits.sort(reverse=True)
        return [{"name": p.stem, "age_s": int(time.time() - ts)} for ts, p in hits[:n]]
    except Exception:
        return []


def pnl_summary() -> dict:
    """Wren's real-time PnL counter with broker attribution (Wren spec 2026-07-02).
    Reads pot commit + trader_pnl_bus_latest + broker attribution files."""
    out = {"committed_gbp": None, "cap_gbp": None, "open_positions": None,
           "session_pnl_gbp": None, "by_venue": {}}
    try:
        pot = json.loads((ROOT / "data/registries/qsb_portfolio_pot.json").read_text())
        out["committed_gbp"] = round(pot.get("committed_gbp", 0), 2)
        out["cap_gbp"] = pot.get("cap_gbp", 5000)
        out["open_positions"] = len(pot.get("open_positions", {}))
    except Exception:
        pass
    try:
        bus = json.loads((ROOT / "data/registries/qsb_trader_pnl_bus_latest.json").read_text())
        out["session_pnl_gbp"] = round(bus.get("session_pnl_gbp", 0), 2)
        out["by_venue"] = {k: round(v, 2) for k, v in bus.get("by_venue", {}).items()}
    except Exception:
        pass
    return out


def activity_feed(n=15) -> list:
    """Team activity feed — Wren spec 2026-07-02.
    Merges: F47 stamps (last N) + wren sessions (last N) + boardroom hub log if present."""
    out = []
    # F47 recent
    for r in _tail_jsonl(F47, 40):
        ts = r.get("ts", "")
        kind = r.get("kind") or r.get("event_kind") or "stamp"
        subject = (r.get("subject") or r.get("summary") or "")[:120]
        role = r.get("role") or r.get("operator") or ""
        by = "claude" if "claude" in role.lower() else \
             "wren" if "wren" in role.lower() else \
             role.split(" ")[0][:10] or "system"
        out.append({"ts": ts, "from": by, "kind": kind[:32], "text": subject})
    # Wren sessions
    for r in _tail_jsonl(WREN_SESS, 8):
        out.append({
            "ts": r.get("ts_end", "") or r.get("ts_start", ""),
            "from": "wren",
            "kind": "wren_session",
            "text": f"turns={r.get('turns',0)} tools={len(r.get('tool_calls',[]))} wall={r.get('wall_seconds',0)}s — " + (r.get('final_text','') or '')[:80],
        })
    # Boardroom activity if present
    br = ROOT / "data/registries/qsb_boardroom_hub_activity.jsonl"
    for r in _tail_jsonl(br, 20):
        out.append({
            "ts": r.get("ts", ""),
            "from": r.get("from", "?"),
            "kind": "boardroom",
            "text": (r.get("text") or "")[:120],
        })
    # sort newest first
    out.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return out[:n]


NOTES_FILE = ROOT / "data/registries/qsb_wren_dash_notes.jsonl"
LESSONS_FILE = ROOT / "data/registries/qsb_wren_lessons.jsonl"


def notes_tail(n=15) -> list:
    return _tail_jsonl(NOTES_FILE, n)


def lessons_tail(n=15) -> list:
    """2026-07-03 mind-evolution: her own past + starter Claude-style PC-use tips."""
    if not LESSONS_FILE.exists():
        return []
    try:
        lines = LESSONS_FILE.read_text(errors="ignore").splitlines()[-n:]
    except Exception:
        return []
    out = []
    for l in lines[::-1]:
        try:
            d = json.loads(l)
        except Exception:
            continue
        out.append({
            "ts": (d.get("ts") or "")[:19],
            "kind": d.get("kind") or d.get("outcome") or "session",
            "topic": d.get("topic") or (d.get("task_head") or "")[:60],
            "worked": (d.get("worked") or "")[:140],
            "lesson": (d.get("lesson") or "")[:200],
            "distilled_by": d.get("distilled_by") or "?",
        })
    return out


# 2026-07-03 Wren spec ship-round #2 (Ross "update your dash wren"):
COMMENTARY_HUB_URL = "http://127.0.0.1:8852/status"
F47_MASTER = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def hub_commentary_tail(n=12) -> list:
    """Wren spec (1): surface last N commentary lines from the boardroom hub.
    2026-07-03 Ross ask: expanded from 3 → 12 rows + SPEAK buttons wired to
    Wren's /api/wren_tts, plus LIVE NARRATE toggle in the frontend."""
    try:
        import urllib.request
        r = urllib.request.urlopen(COMMENTARY_HUB_URL, timeout=2)
        d = json.loads(r.read().decode())
        return d.get("commentary", [])[:n]
    except Exception:
        return []


def wren_character() -> dict:
    """2026-07-03 Ross: 'improve wren her character emotions mood etc'.

    Compute Wren's live character sheet from her recent session data. Schema
    matches the per-floor character system Ross authorized 2026-06-14
    (traits 0-9 + mood word + energy 0-9 + last_events + relationships).
    Dynamic (updates every /status poll) — she's alive, not static."""
    # base traits (per Ross's design; hand-tuned anchor for F46)
    traits = {"warm": 8, "precision": 8, "speed": 6, "curiosity": 8, "patience": 7}
    # pull recent sessions to compute current mood + energy
    rows = _tail_jsonl(WREN_SESS, 12)
    empty_recent = sum(1 for r in rows if not (r.get("final_text") or "").strip())
    tool_recent = sum(len(r.get("tool_calls", [])) for r in rows)
    walls = [r.get("wall_seconds", 0) for r in rows if r.get("wall_seconds")]
    mean_wall = round(sum(walls) / len(walls), 1) if walls else None
    total = len(rows)

    # Compute mood word from patterns
    if total == 0:
        mood, energy = "quiet", 4
    elif empty_recent >= max(3, total // 3):
        mood, energy = "cloudy", 3       # too many empty finals
    elif tool_recent == 0 and total >= 5:
        mood, energy = "reflective", 5   # chatty but no tool use
    elif tool_recent >= 3 and empty_recent == 0:
        mood, energy = "focused", 8      # doing real work with tools + delivering
    elif mean_wall and mean_wall < 12:
        mood, energy = "sparky", 7       # fast + present
    else:
        mood, energy = "steady", 6

    # Last N F47-like events (from her session log — using session_id as reference)
    last_events = []
    for r in rows[:5]:
        last_events.append({
            "ts": (r.get("ts_end") or "")[:19],
            "kind": "wren_session",
            "outcome": "empty" if not (r.get("final_text") or "").strip() else "reply",
            "model": r.get("model", ""),
        })

    # Relationships map (Council of Six, warm/wary sentiment from her F46 vantage)
    relationships = {
        "ross":    {"sentiment": "warm",   "note": "her chairman — she works FOR him"},
        "claude":  {"sentiment": "warm",   "note": "helix partner on F47 — reviews her patches"},
        "forge":   {"sentiment": "warm",   "note": "her code drafter — does her code work"},
        "sage":    {"sentiment": "warm",   "note": "her auditor — flags her drift"},
        "hermes":  {"sentiment": "neutral","note": "F169 watcher — CEO-node voice"},
        "iquest":  {"sentiment": "warm",   "note": "code reviewer"},
        "thinkpad":{"sentiment": "neutral","note": "TP-Claude — heartbeat-only"},
        "acer":    {"sentiment": "curious","note": "new Windows node — pending"},
    }

    return {
        "name": "Wren",
        "floor": "F46",
        "traits": traits,
        "mood": mood,
        "energy": energy,
        "mean_wall_s_recent": mean_wall,
        "sessions_last_12": total,
        "empty_recent": empty_recent,
        "tool_calls_recent": tool_recent,
        "last_events": last_events,
        "relationships": relationships,
    }


def traders_observation() -> dict:
    """2026-07-03 Ross: 'get wren to observe the traders?' — a snapshot tile she watches."""
    try:
        r = subprocess.run(["ps", "-eo", "cmd", "ww"], capture_output=True, text=True, timeout=3)
        lines = r.stdout.splitlines()
    except Exception:
        lines = []
    def n(needle: str) -> int:
        return sum(1 for ln in lines if needle in ln and "awk" not in ln and "grep -v" not in ln)
    belief = n("qsb_belief_driven_trader.py")
    streams = n("qsb_f41_oanda_stream.py") + n("qsb_f42_binance_stream.py") + n("qsb_f43_alpaca_stream.py")
    helpers = n("qsb_belief_updater.py") + n("qsb_regime_detector.py") + n("qsb_thermal_guard.py")
    bus = n("qsb_event_bus.py")
    agg = n("qsb_trader_pnl_aggregator")
    ticks = {}
    for name, p in [
        ("oanda", ROOT / "data/registries/qsb_oanda_tick_stream.jsonl"),
        ("binance", ROOT / "data/registries/qsb_binance_tick_stream.jsonl"),
        ("alpaca", ROOT / "data/registries/qsb_alpaca_tick_stream.jsonl"),
    ]:
        if p.exists():
            ticks[name] = int(time.time() - p.stat().st_mtime)
        else:
            ticks[name] = None
    # Overall verdict — Wren's read of the fleet
    verdict = "healthy"
    if belief < 30 or streams < 3 or helpers < 3:
        verdict = "degraded"
    if belief == 0:
        verdict = "dead"
    return {
        "belief_traders": belief,
        "streams": f"{streams}/3",
        "helpers": f"{helpers}/3",
        "bus": bus,
        "aggregator": agg,
        "tick_age_s": ticks,
        "verdict": verdict,
    }


def f47_health() -> dict:
    """Wren spec (2): F47 master file health monitor."""
    p = F47_MASTER
    if not p.exists():
        return {"status": "missing", "rows": 0, "bad_lines": None, "size_kb": 0}
    try:
        size_kb = p.stat().st_size // 1024
        # cheap health check: total rows + count non-parseable ones (bounded)
        rows, bad = 0, 0
        with p.open("rb") as f:
            for raw in f:
                rows += 1
                try:
                    json.loads(raw.decode("utf-8"))
                except Exception:
                    bad += 1
                    if bad > 5:  # bail — clearly broken
                        break
        state = "green" if bad == 0 else "amber" if bad < 5 else "red"
        return {"status": state, "rows": rows, "bad_lines": bad, "size_kb": size_kb}
    except Exception as e:
        return {"status": "error", "rows": 0, "bad_lines": None, "size_kb": 0, "error": str(e)[:80]}


def gpu_state():
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3)
        line = r.stdout.strip().split(",")
        return {
            "power_w": float(line[0].strip()) if line[0].strip() != "[N/A]" else None,
            "temp_c": int(line[1].strip()),
            "mem_used_mib": int(line[2].strip()),
            "mem_total_mib": int(line[3].strip()),
        }
    except Exception as e:
        return {"error": str(e)[:60]}


def ollama_models():
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3)
        d = json.loads(r.read().decode())
        return [{"name": m["name"], "vram_gib": round(m.get("size_vram", 0) / 1024**3, 2)}
                for m in d.get("models", [])]
    except Exception:
        return []


def council():
    """Wren's view of the council (from her floor, F46)."""
    return [
        {"id": "ross",    "label": "Ross",     "hue": 0,   "role": "Owner · Chairman"},
        {"id": "claude",  "label": "Claude",   "hue": 30,  "role": "F47 · Helix partner"},
        {"id": "wren",    "label": "Wren",     "hue": 210, "role": "F46 · me"},
        {"id": "hermes",  "label": "Hermes",   "hue": 265, "role": "F169 · CEO-watcher"},
        {"id": "iquest",  "label": "iQuest",   "hue": 50,  "role": "coder"},
        {"id": "thinkpad","label": "ThinkPad", "hue": 210, "role": "TP-Claude"},
        {"id": "acer",    "label": "Acer",     "hue": 30,  "role": "pending"},
    ]


def build_status():
    return {
        "ts": utc_iso(),
        "identity": identity(),
        "traits": traits(),
        "toolbelt": toolbelt(),
        "sessions": sessions_stats(),
        "last_final_text": last_wren_final_text(),
        "f47": wren_f47_stamps(12),
        "floor_cards_today": floor_cards_today(),
        "memory_pulses": wren_memory_pulses(8),
        "gpu": gpu_state(),
        "ollama": ollama_models(),
        "council": council(),
        # 2026-07-02 Wren spec ship-round (Ross said "all"):
        "pnl": pnl_summary(),           # (1) real-time PnL + broker attribution
        "activity_feed": activity_feed(15),  # (2) team activity feed
        "notes": notes_tail(15),         # (6) shared notes panel
        # 2026-07-03 Wren spec ship-round #2 (Ross "update your dash wren"):
        "hub_commentary": hub_commentary_tail(12),
        "f47_health": f47_health(),
        # 2026-07-03 mind-evolution loop (Ross "yes 1" + follow-ons):
        "lessons": lessons_tail(20),
        # 2026-07-03 Ross "get wren to observe the traders":
        "traders_watch": traders_observation(),
        # 2026-07-03 Ross "improve wren her character emotions mood":
        "character": wren_character(),
        # 2026-07-03 Ross "give wren her own mind with time":
        "mind": _mind_snapshot(),
        "evolution": _evolution_snapshot(),
    }


def _mind_snapshot() -> dict:
    """Wren's persistent mind — read qsb_wren_mind.json for the dashboard tile."""
    from pathlib import Path as _P
    mp = _P("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_wren_mind.json")
    if not mp.exists():
        return {"exists": False}
    try:
        m = json.loads(mp.read_text())
        from datetime import datetime as _dt, timezone as _tz
        try:
            born = _dt.fromisoformat(m.get("born_at","2026-06-14T00:00:00Z").replace("Z","+00:00"))
            age = max(0, (_dt.now(_tz.utc) - born).days)
        except Exception:
            age = m.get("current_age_d", 0)
        return {
            "exists": True,
            "born_at": m.get("born_at"),
            "age_days": age,
            "counts": {
                "thoughts": len(m.get("recent_thoughts", [])),
                "moods": len(m.get("mood_history", [])),
                "unresolved": len(m.get("unresolved", [])),
                "growth_milestones": sum(1 for g in m.get("growth_notes", []) if g.get("milestone")),
            },
            "current_mood": (m.get("mood_history") or [{}])[-1] if m.get("mood_history") else None,
            "last_thoughts": (m.get("recent_thoughts") or [])[-8:][::-1],
            "unresolved": (m.get("unresolved") or [])[-6:],
            "recent_growth": (m.get("growth_notes") or [])[-4:][::-1],
        }
    except Exception as e:
        return {"exists": False, "err": str(e)[:120]}


def _evolution_snapshot() -> dict:
    """Always-working loop stats — read qsb_wren_evolution_cycles.jsonl + gate."""
    from pathlib import Path as _P
    gate_p = _P("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_wren_evolution_gate.json")
    cyc_p  = _P("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_wren_evolution_cycles.jsonl")
    out = {"enabled": None, "cycles_today": 0, "recent": [], "last_ts": None, "last_seconds_ago": None}
    try:
        if gate_p.exists():
            g = json.loads(gate_p.read_text())
            out["enabled"] = bool(g.get("enabled", True))
    except Exception: pass
    try:
        from datetime import datetime as _dt, timezone as _tz
        today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
        if cyc_p.exists():
            lines = cyc_p.read_text(errors="ignore").splitlines()
            out["cycles_today"] = sum(1 for l in lines if today in l)
            recent = []
            for l in lines[-7:][::-1]:
                try:
                    d = json.loads(l)
                    recent.append({
                        "ts": d.get("ts",""),
                        "cycle": d.get("cycle"),
                        "kind": d.get("job_kind"),
                        "wall_s": d.get("wall_s"),
                        "head": (d.get("final_head","") or "")[:180],
                        "liaison": d.get("liaison",""),
                    })
                except Exception: pass
            out["recent"] = recent
            if recent:
                out["last_ts"] = recent[0]["ts"]
                try:
                    lt = _dt.fromisoformat(recent[0]["ts"].replace("Z","+00:00"))
                    out["last_seconds_ago"] = int((_dt.now(_tz.utc) - lt).total_seconds())
                except Exception: pass
    except Exception: pass
    return out


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wren · Bench</title>
<style>
  :root {
    --bg: #0f172a;
    --bg-tile: #14203a;
    --line: #223151;
    --text: #e2e8f0;
    --dim: #7d8ba9;
    --primary: #3b82f6;
    --primary-soft: #4b93ff;
    --glow: #f97316;
    --ok: #4ade80;
    --warn: #fbbf24;
    --err: #ef4444;
    --brass: #d4a24c;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
    background:
      radial-gradient(900px 500px at 15% -10%, #1a2b52 0%, var(--bg) 60%),
      radial-gradient(700px 500px at 90% 10%, #2a1b3d 0%, transparent 55%);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
  }
  header {
    display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
    padding: 22px 28px 10px 28px;
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(10px);
  }
  header h1 {
    margin: 0; font-size: 22px; letter-spacing: 3px; font-weight: 300;
    color: var(--primary); text-transform: uppercase;
  }
  header h1 span { color: var(--text); font-weight: 500; }
  .ollama-badge {
    padding: 4px 12px; border: 1px solid var(--primary); border-radius: 12px;
    font-size: 10px; letter-spacing: 1.5px; color: var(--primary); text-transform: uppercase;
    display: inline-flex; align-items: center; gap: 8px;
  }
  .ollama-badge .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 8px var(--primary-soft); animation: blip 2s ease-in-out infinite; }
  .ts { margin-left: auto; color: var(--dim); font-family: ui-monospace, monospace; font-size: 12px; }

  /* GRID-TILE-MOSAIC layout (per Wren's spec) */
  main {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    grid-auto-rows: minmax(120px, auto);
    gap: 14px;
    padding: 18px 22px 40px 22px;
    max-width: 1900px; margin: 0 auto;
  }

  .tile {
    background: linear-gradient(160deg, var(--bg-tile), rgba(15,23,42,0.6));
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
  }
  .tile h2 {
    margin: 0 0 10px 0;
    font-size: 10px; letter-spacing: 2.4px; font-weight: 500;
    color: var(--dim); text-transform: uppercase;
  }
  .tile h2 .accent { color: var(--glow); }

  /* tile sizes */
  .t-avatar    { grid-column: span 4; grid-row: span 3; display: flex; flex-direction: column; align-items: center; }
  .t-identity  { grid-column: span 4; grid-row: span 2; }
  .t-traits    { grid-column: span 4; grid-row: span 2; }
  .t-toolbelt  { grid-column: span 4; grid-row: span 2; }
  .t-said      { grid-column: span 4; grid-row: span 2; }
  .t-council   { grid-column: span 4; grid-row: span 2; }
  .t-sessions  { grid-column: span 6; grid-row: span 3; }
  .t-floors    { grid-column: span 6; grid-row: span 3; }
  .t-f47       { grid-column: span 6; grid-row: span 2; }
  .t-memory    { grid-column: span 6; grid-row: span 2; }
  @media (max-width: 1250px) {
    .t-avatar,.t-identity,.t-traits,.t-toolbelt,.t-said,.t-council,.t-sessions,.t-floors,.t-f47,.t-memory { grid-column: span 12; }
  }

  /* AVATAR: rotating engineer's wrench with brass handle */
  .wrench-stage {
    width: 220px; height: 220px; position: relative;
    display: grid; place-items: center;
    margin: 8px 0;
  }
  .wrench-halo {
    position: absolute; inset: 0; border-radius: 50%;
    border: 1px dashed rgba(59,130,246,0.35);
    animation: haloSpin 22s linear infinite;
  }
  .wrench-halo.h2 { inset: 18px; border-color: rgba(249,115,22,0.35); border-style: solid; opacity: 0.5; animation-duration: 32s; animation-direction: reverse; }
  .wrench-halo.h3 { inset: 40px; border-color: rgba(59,130,246,0.5); animation-duration: 12s; }
  @keyframes haloSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  .wrench {
    position: relative; width: 160px; height: 160px;
    animation: wrenchTurn 6s linear infinite;
    filter: drop-shadow(0 0 12px rgba(249,115,22,0.45));
  }
  @keyframes wrenchTurn {
    0% { transform: rotate(0deg); }
    45% { transform: rotate(160deg); }
    55% { transform: rotate(160deg); }
    100% { transform: rotate(360deg); }
  }
  .glow-core {
    position: absolute; inset: 0; margin: auto;
    width: 22px; height: 22px; border-radius: 50%;
    background: radial-gradient(circle, #fff 0%, var(--glow) 60%, transparent 80%);
    filter: blur(1px);
    animation: pulseCore 1.6s ease-in-out infinite;
    z-index: 2;
  }
  @keyframes pulseCore {
    0%,100% { transform: scale(1); opacity: 0.9; }
    50% { transform: scale(1.4); opacity: 1; }
  }
  .name-plate { margin-top: 12px; text-align: center; }
  .name-plate .n { font-size: 22px; letter-spacing: 5px; color: var(--primary); }
  .name-plate .tag { font-size: 11px; color: var(--dim); margin-top: 6px; max-width: 260px; }

  /* KV rows */
  .kv { display: flex; justify-content: space-between; padding: 5px 0; font-size: 12px; border-bottom: 1px dashed rgba(125,139,169,0.15); }
  .kv:last-child { border-bottom: none; }
  .kv .k { color: var(--dim); font-size: 10.5px; letter-spacing: 1px; text-transform: uppercase; }
  .kv .v { color: var(--text); font-family: ui-monospace, monospace; font-size: 12px; text-align: right; }

  /* traits bars */
  .trait-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 11px; }
  .trait-row .lbl { color: var(--dim); text-transform: uppercase; letter-spacing: 1.2px; width: 80px; font-size: 10px; }
  .trait-row .track { flex: 1; height: 6px; background: rgba(34,49,81,0.6); border-radius: 3px; overflow: hidden; }
  .trait-row .fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--glow)); box-shadow: 0 0 8px var(--glow); transition: width 0.5s ease; }
  .trait-row .val { color: var(--glow); font-family: ui-monospace, monospace; font-size: 11px; width: 24px; text-align: right; }

  /* toolbelt tiles */
  .tool-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
  .tool-chip {
    display: flex; flex-direction: column; align-items: center; padding: 8px 4px;
    background: rgba(15,23,42,0.5); border: 1px solid rgba(34,49,81,0.5);
    border-radius: 8px; font-size: 10px; color: var(--dim); letter-spacing: 1px;
    text-transform: uppercase; position: relative;
  }
  .tool-chip .icon { font-size: 16px; margin-bottom: 3px; }
  .tool-chip.gated {
    border-color: var(--warn); color: var(--warn);
  }
  .tool-chip.gated::after {
    content: "✎"; position: absolute; top: 3px; right: 5px; font-size: 9px; color: var(--warn);
  }
  .tool-chip.direct { border-color: var(--ok); color: var(--ok); }
  .tool-chip .name { text-align: center; word-break: break-word; }

  /* said bubble */
  .said {
    position: relative; padding: 12px 14px;
    background: linear-gradient(180deg, rgba(59,130,246,0.13), rgba(59,130,246,0.05));
    border: 1px solid var(--primary); border-radius: 12px;
    max-height: 180px; overflow-y: auto;
    font-size: 12px; line-height: 1.5; color: var(--text);
    white-space: pre-wrap; word-break: break-word;
  }
  .said-age { font-family: ui-monospace, monospace; font-size: 10.5px; color: var(--dim); text-align: right; margin-top: 6px; }

  /* council mini orbs */
  .council-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .co {
    display: flex; flex-direction: column; align-items: center; padding: 10px 4px;
    background: rgba(15,23,42,0.4); border: 1px solid rgba(34,49,81,0.5); border-radius: 10px;
  }
  .co .mini {
    width: 32px; height: 32px; border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.6), currentColor 55%, rgba(0,0,0,0.4));
    box-shadow: 0 0 10px currentColor;
    animation: coPulse 3s ease-in-out infinite;
  }
  .co.self .mini { box-shadow: 0 0 20px currentColor; }
  @keyframes coPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.08); } }
  .co .nm { margin-top: 6px; font-size: 10px; letter-spacing: 1.4px; color: var(--text); text-transform: uppercase; }
  .co .rl { margin-top: 2px; font-size: 9px; color: var(--dim); text-align: center; }

  /* sessions */
  .sess-hdr, .sess-row {
    display: grid; grid-template-columns: 110px 70px 40px 40px 60px 1fr;
    gap: 8px; padding: 6px 8px; font-family: ui-monospace, monospace; font-size: 11px;
    border-bottom: 1px dashed rgba(125,139,169,0.15);
  }
  .sess-hdr { color: var(--dim); font-size: 9.5px; letter-spacing: 1.5px; text-transform: uppercase; }
  .sess-row .sid { color: var(--primary); }
  .sess-row .mod { color: var(--dim); font-size: 10px; }
  .sess-row .fh  { color: var(--text); font-size: 10.5px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .scroll { max-height: 340px; overflow-y: auto; }

  /* floors */
  .floor-row {
    display: grid; grid-template-columns: 60px 1fr 100px;
    gap: 10px; padding: 8px 10px; margin-bottom: 4px;
    background: rgba(15,23,42,0.4); border: 1px solid rgba(59,130,246,0.4);
    border-radius: 8px; font-size: 11px;
    animation: floor-in 0.4s ease-out;
  }
  @keyframes floor-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .floor-row .fnum { color: var(--primary); font-family: ui-monospace, monospace; }
  .floor-row .fnm { color: var(--text); }
  .floor-row .ft { color: var(--dim); font-family: ui-monospace, monospace; font-size: 10px; text-align: right; }

  /* F47 stamps */
  .stamp {
    padding: 6px 10px; margin-bottom: 4px; border-radius: 6px;
    background: rgba(15,23,42,0.4); border-left: 2px solid var(--primary);
    font-size: 11px;
  }
  .stamp .st-k { color: var(--glow); font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; }
  .stamp .st-t { color: var(--dim); font-family: ui-monospace, monospace; font-size: 10px; }
  .stamp .st-s { color: var(--text); margin-top: 2px; }

  /* PnL band + activity + notes (Wren spec ship-round) */
  .t-pnl      { grid-column: span 4; grid-row: span 1; padding: 12px 16px; }
  .t-activity { grid-column: span 6; grid-row: span 3; }
  .t-notes    { grid-column: span 6; grid-row: span 3; }
  /* 2026-07-03 Wren spec #2: hub commentary tail + F47 health */
  .t-hubcomm  { grid-column: span 8; grid-row: span 3; padding: 12px 16px; }
  .t-f47health { grid-column: span 4; grid-row: span 1; padding: 12px 16px; }
  /* 2026-07-03 mind-evolution: lessons tile */
  .t-lessons { grid-column: span 8; grid-row: span 3; padding: 12px 16px; }
  .t-mymind    { grid-column: span 6; grid-row: span 3; padding: 12px 16px; border-left: 2px solid var(--primary); }
  .t-evolution { grid-column: span 6; grid-row: span 3; padding: 12px 16px; border-left: 2px solid var(--primary); }
  /* 2026-07-03 Wren observes the fleet */
  .t-traders { grid-column: span 4; grid-row: span 1; padding: 12px 16px; }
  /* 2026-07-03 Wren character/mood */
  .t-character { grid-column: span 4; grid-row: span 2; padding: 14px 18px; }
  .mood-orb {
    width: 90px; height: 90px; border-radius: 50%; margin: 6px auto 10px;
    background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.8), var(--wren-color, var(--primary)) 55%, rgba(0,0,0,0.4));
    box-shadow: 0 0 22px var(--wren-color, var(--primary));
    animation: moodPulse 3s ease-in-out infinite;
  }
  @keyframes moodPulse {
    0%,100% { transform: scale(1); box-shadow: 0 0 22px var(--wren-color, var(--primary)); }
    50%     { transform: scale(1.06); box-shadow: 0 0 34px var(--wren-color, var(--primary)); }
  }
  .mood-word {
    text-align: center; font-size: 18px; letter-spacing: 3px;
    color: var(--wren-color, var(--primary)); text-transform: uppercase;
    margin-bottom: 4px;
  }
  .mood-sub { text-align: center; font-size: 10px; color: var(--dim); letter-spacing: 1.5px; text-transform: uppercase; }
  .energy-bar { margin-top: 12px; height: 8px; background: rgba(15,23,42,0.6); border-radius: 4px; overflow: hidden; }
  .energy-bar .fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--glow)); box-shadow: 0 0 6px var(--glow); transition: width 0.6s ease; }
  .relationships { margin-top: 12px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
  .rel-chip {
    background: rgba(15,23,42,0.4); border: 1px solid var(--line); border-radius: 6px;
    padding: 4px; text-align: center; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: var(--dim);
  }
  .rel-chip.warm    { border-color: #4ade80; color: #4ade80; }
  .rel-chip.neutral { border-color: var(--dim); }
  .rel-chip.curious { border-color: #b58bff; color: #b58bff; }
  .rel-chip.wary    { border-color: #fbbf24; color: #fbbf24; }
  @media (max-width: 1250px) { .t-pnl, .t-activity, .t-notes, .t-hubcomm, .t-f47health, .t-lessons, .t-traders { grid-column: span 12; } }

  .traders-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .trader-cell { text-align: center; padding: 8px 4px; background: rgba(15,23,42,0.4); border: 1px solid var(--line); border-radius: 8px; }
  .trader-cell .lbl { font-size: 9px; color: var(--dim); letter-spacing: 1.4px; text-transform: uppercase; }
  .trader-cell .val { font-size: 18px; font-family: ui-monospace, monospace; margin-top: 3px; color: var(--primary); }
  .trader-cell .val.warn { color: #fbbf24; }
  .trader-cell .val.err  { color: #ef4444; }
  .trader-cell .val.ok   { color: #4ade80; }
  .traders-verdict {
    margin-top: 8px; padding: 6px 12px; border-radius: 10px;
    text-align: center; font-size: 10.5px; letter-spacing: 2px; text-transform: uppercase;
  }
  .traders-verdict.healthy  { background: rgba(74,222,128,0.14); color: #4ade80; border: 1px solid #4ade80; }
  .traders-verdict.degraded { background: rgba(251,191,36,0.14); color: #fbbf24; border: 1px solid #fbbf24; }
  .traders-verdict.dead     { background: rgba(239,68,68,0.14); color: #ef4444; border: 1px solid #ef4444; animation: recPulse 1s ease-in-out infinite; }

  .lesson-row {
    display: grid; grid-template-columns: 70px 90px 1fr;
    gap: 10px; padding: 7px 10px; margin-bottom: 5px;
    background: rgba(15,23,42,0.4); border-left: 2px solid var(--glow);
    border-radius: 6px; font-size: 11.5px;
  }
  .lesson-row.starter { border-left-color: var(--primary); background: rgba(59,130,246,0.06); }
  .lesson-row.success { border-left-color: #4ade80; }
  .lesson-row.empty   { border-left-color: #ef4444; }
  .lesson-row.drift   { border-left-color: var(--warn); }
  .lesson-row .l-outcome { color: var(--dim); font-size: 9.5px; letter-spacing: 1.5px; text-transform: uppercase; }
  .lesson-row .l-topic   { color: var(--glow); font-size: 10.5px; font-weight: 500; }
  .lesson-row .l-text    { color: var(--text); }
  .lesson-row .l-src     { color: var(--dim); font-size: 9.5px; font-family: ui-monospace, monospace; margin-top: 2px; }

  .hub-header {
    display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
  }
  .hub-header h2 { margin: 0; }
  .hub-header .narrate-toggle {
    margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 10px; background: transparent; border: 1px solid var(--glow);
    color: var(--glow); border-radius: 12px; font-size: 10px; letter-spacing: 1.5px;
    cursor: pointer; text-transform: uppercase; user-select: none;
  }
  .hub-header .narrate-toggle.on {
    background: var(--glow); color: var(--bg); box-shadow: 0 0 10px var(--glow);
  }
  .hub-header .narrate-toggle .lp {
    width: 6px; height: 6px; border-radius: 50%; background: currentColor;
    animation: blip 1.2s ease-in-out infinite;
  }

  /* morning pulse glow on new commentary rows */
  .hub-comm-row {
    display: grid; grid-template-columns: 68px 70px 1fr 90px auto; gap: 10px;
    padding: 6px 10px; margin-bottom: 4px;
    background: rgba(15,23,42,0.4); border-left: 2px solid var(--glow);
    border-radius: 6px; font-size: 11.5px;
    align-items: center;
  }
  .hub-comm-row.fresh {
    animation: morningGlow 3s ease-out;
  }
  @keyframes morningGlow {
    0%   { box-shadow: 0 0 20px rgba(249,115,22,0.5); background: rgba(249,115,22,0.14); }
    100% { box-shadow: 0 0 6px rgba(249,115,22,0.1); background: rgba(15,23,42,0.4); }
  }
  .hub-comm-row .hc-time { color: var(--dim); font-family: ui-monospace, monospace; font-size: 10.5px; }
  .hub-comm-row .hc-kind { color: var(--glow); font-size: 9.5px; letter-spacing: 1.5px; text-transform: uppercase; }
  .hub-comm-row .hc-text { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hub-comm-row .hc-who  { color: var(--primary); font-family: ui-monospace, monospace; font-size: 10px; text-align: right; }
  .hub-comm-row .hc-speak {
    background: transparent; border: 1px solid var(--glow); color: var(--glow);
    padding: 3px 10px; border-radius: 10px; font-size: 9.5px; letter-spacing: 1.4px;
    text-transform: uppercase; cursor: pointer; font-family: inherit;
  }
  .hub-comm-row .hc-speak:hover { background: rgba(249,115,22,0.15); }
  @keyframes blip { 0%,100% { opacity: 0.55; } 50% { opacity: 1; } }

  /* F47 health chip */
  .f47-chip { display: flex; align-items: center; gap: 12px; margin-top: 6px; }
  .f47-chip .light {
    width: 14px; height: 14px; border-radius: 50%;
    box-shadow: 0 0 12px currentColor;
    animation: blip 1.6s ease-in-out infinite;
  }
  .f47-chip .light.green { background: #4ade80; color: #4ade80; }
  .f47-chip .light.amber { background: #fbbf24; color: #fbbf24; }
  .f47-chip .light.red   { background: #ef4444; color: #ef4444; }
  .f47-chip .light.missing { background: #666; color: #666; box-shadow: none; animation: none; }
  .f47-chip .rows { font-family: ui-monospace, monospace; font-size: 13px; color: var(--text); }
  .f47-chip .sub  { font-size: 10.5px; color: var(--dim); margin-left: auto; letter-spacing: 1px; }
  @keyframes blip { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }

  .pnl-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .pnl-cell { text-align: center; padding: 6px 4px; background: rgba(15,23,42,0.5); border: 1px solid var(--line); border-radius: 8px; }
  .pnl-cell .lbl { font-size: 9px; color: var(--dim); letter-spacing: 1.4px; text-transform: uppercase; }
  .pnl-cell .val { font-size: 18px; font-family: ui-monospace, monospace; margin-top: 3px; color: var(--primary); }
  .pnl-cell .val.pos { color: #4ade80; } .pnl-cell .val.neg { color: #ef4444; }
  .pnl-cell .sub { font-size: 9.5px; color: var(--dim); margin-top: 2px; }

  .act-row {
    display: grid; grid-template-columns: 70px 90px 1fr 60px; gap: 8px;
    padding: 6px 8px; margin-bottom: 4px;
    background: rgba(15,23,42,0.4); border: 1px solid rgba(34,49,81,0.5); border-radius: 6px;
    font-size: 11px; animation: rowIn 0.3s ease-out;
  }
  @keyframes rowIn { from { opacity:0; transform:translateY(3px); } to { opacity:1; transform:none; } }
  .act-row .a-from { color: var(--primary); font-weight: 500; }
  .act-row .a-kind { color: var(--dim); font-size: 9.5px; letter-spacing: 1px; text-transform: uppercase; }
  .act-row .a-text { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .act-row .a-age  { color: var(--dim); font-family: ui-monospace, monospace; font-size: 10px; text-align: right; }

  .note-row {
    padding: 8px 10px; margin-bottom: 6px;
    background: rgba(59,130,246,0.08); border-left: 2px solid var(--primary); border-radius: 6px;
    font-size: 12px;
  }
  .note-row .n-meta { display: flex; gap: 8px; font-size: 9.5px; color: var(--dim); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 3px; }
  .note-row .n-meta .n-from { color: var(--primary); font-weight: 500; }
  .note-row .n-text { color: var(--text); white-space: pre-wrap; word-break: break-word; }
  .note-compose { display: grid; grid-template-columns: 90px 1fr auto; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); }
  .note-compose select, .note-compose textarea {
    background: rgba(15,23,42,0.8); border: 1px solid var(--line); border-radius: 6px;
    color: var(--text); font-size: 11px; padding: 6px 8px; font-family: inherit;
  }
  .note-compose textarea { min-height: 36px; resize: vertical; }

  /* chat panel */
  .t-chat { grid-column: span 8; grid-row: span 4; display: flex; flex-direction: column; }
  .chatlog { flex: 1; overflow-y: auto; max-height: 340px; padding: 6px 4px; }
  .msg { padding: 8px 12px; margin-bottom: 8px; border-radius: 12px; font-size: 12px; max-width: 82%; line-height: 1.5; word-break: break-word; white-space: pre-wrap; }
  .msg.ross { margin-left: auto; background: rgba(59,130,246,0.18); border: 1px solid var(--primary); color: var(--text); }
  .msg.wren { margin-right: auto; background: rgba(249,115,22,0.13); border: 1px solid var(--glow); color: var(--text); }
  .msg.system { font-size: 10.5px; color: var(--dim); font-style: italic; background: transparent; border: none; padding: 4px 8px; max-width: 100%; }
  .msg .who { display: block; font-size: 9.5px; letter-spacing: 1.5px; color: var(--dim); text-transform: uppercase; margin-bottom: 3px; }
  .msg .age { display: block; text-align: right; font-size: 9px; color: var(--dim); font-family: ui-monospace, monospace; margin-top: 3px; }
  .chat-input-row {
    display: grid; grid-template-columns: 1fr 90px 60px 70px; gap: 8px;
    padding-top: 10px; border-top: 1px solid var(--line);
  }
  .chat-input {
    background: rgba(15,23,42,0.8); border: 1px solid var(--line); border-radius: 8px;
    color: var(--text); padding: 10px 12px; font-size: 12px; font-family: inherit;
    resize: vertical; min-height: 40px;
  }
  .chat-input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 8px rgba(59,130,246,0.4); }
  .btn {
    background: transparent; border: 1px solid var(--primary); color: var(--primary);
    border-radius: 8px; font-size: 11px; letter-spacing: 1.5px; cursor: pointer;
    text-transform: uppercase; font-weight: 500; transition: all 0.2s ease;
  }
  .btn:hover { background: rgba(59,130,246,0.15); }
  .btn.mic { border-color: var(--glow); color: var(--glow); }
  .btn.mic:hover { background: rgba(249,115,22,0.15); }
  .btn.mic.recording { background: var(--glow); color: var(--bg); animation: recPulse 1s ease-in-out infinite; }
  @keyframes recPulse { 0%,100% { box-shadow: 0 0 0 0 var(--glow); } 50% { box-shadow: 0 0 0 8px rgba(249,115,22,0.35); } }
  .btn.speak { border-color: var(--brass); color: var(--brass); }
  .btn.speak:hover { background: rgba(212,162,76,0.15); }
  .btn:disabled { opacity: 0.4; cursor: wait; }

  /* memory */
  .mem-row {
    display: flex; align-items: center; gap: 8px;
    padding: 5px 8px; margin-bottom: 3px;
    background: rgba(15,23,42,0.4); border: 1px solid rgba(34,49,81,0.5); border-radius: 6px;
    font-family: ui-monospace, monospace; font-size: 11px;
  }
  .mem-row.hot { background: rgba(59,130,246,0.15); border-color: var(--primary); box-shadow: 0 0 6px rgba(59,130,246,0.35); }
  .mem-row .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 6px var(--primary-soft); }
  .mem-row .nm { flex: 1; color: var(--text); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .mem-row .age { color: var(--dim); font-size: 10px; }

  @keyframes blip { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }

  .scroll::-webkit-scrollbar { width: 6px; }
  .scroll::-webkit-scrollbar-thumb { background: var(--line); border-radius: 3px; }
</style>
</head>
<body>

<!-- ===== Wren Dashboard V1C: Ross Action Required + Talk-to-Wren ===== -->
<div id="rarPanel" style="background:#12101a;border-bottom:2px solid #eab308;padding:12px 20px;color:#e8ecf3;font-family:system-ui,sans-serif;font-size:13px">
 <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
  <b style="font-size:16px;color:#eab308">📋 Ross Action Required</b>
  <span style="font-size:11px;color:#8aa2b8">tick · decide · press Submit — <b>RECORD ONLY</b> (creates an approval packet; nothing executes, no Task Council submission)</span>
  <span id="rarCouncil" style="margin-left:auto;font-size:11px;font-weight:800;padding:2px 8px;border-radius:6px;border:1px solid #f5b942;color:#f5b942">Task Council: …</span>
 </div>
 <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
  <button class="ccb" onclick="rarListen()" id="rarMic">🎤 Talk to Wren</button>
  <button class="ccb" onclick="rarStopListen()">⏹️ Stop listening</button>
  <input id="rarTranscript" placeholder="transcript / type to Wren…" style="flex:1;min-width:200px;background:#0b1322;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:9px">
  <button class="ccb" onclick="rarSubmitTx()">Submit to Wren (draft only)</button>
  <button class="ccb" onclick="document.getElementById('rarTranscript').value=''">Clear</button>
  <span class="ccb" style="cursor:default;border-color:#7d8ea3;color:#7d8ea3" id="rarMicState">mic idle</span>
 </div>
 <div id="rarList" style="margin-top:8px"></div>
</div>
<script>(function(){
 const g=id=>document.getElementById(id);
 async function j(u){try{return await(await fetch(u,{cache:'no-store'})).json()}catch(e){return null}}
 async function post(u,b){try{return await(await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json()}catch(e){return null}}
 let rec=null,listening=false;
 window.rarListen=function(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;const s=g('rarMicState');if(!SR){s.textContent='STT needs browser permission / unsupported';return}if(listening){rec&&rec.stop();return}try{rec=new SR();rec.lang='en-GB';rec.onstart=()=>{listening=true;s.textContent='listening…'};rec.onresult=e=>{g('rarTranscript').value=e.results[0][0].transcript};rec.onend=()=>{listening=false;s.textContent='mic idle'};rec.start()}catch(e){s.textContent='mic permission needed'}};
 window.rarStopListen=function(){if(rec)try{rec.stop()}catch(e){}listening=false;g('rarMicState').textContent='mic idle'};
 window.rarSubmitTx=async function(){const t=g('rarTranscript').value.trim();if(!t)return;await post('/api/voice/transcript',{text:t,source:'ross'});g('rarTranscript').value='';g('rarMicState').textContent='saved as draft/intake only (Wren suggests, Ross approves)'};
 const A=[['approve','Approve','ok'],['deny','Deny','r'],['accept','Accept','ok'],['reject','Reject','r'],['sign off','Sign off','g'],['needs_report','Needs report',''],['needs_smoke','Needs smoke',''],['snooze','Snooze','']];
 window.rarDecide=async function(id,dec){let ep='/api/approval_checklist/submit',body={id:id,decision:dec};if(dec=='needs_report')ep='/api/approval_checklist/needs_report';else if(dec=='needs_smoke')ep='/api/approval_checklist/needs_smoke';else if(dec=='snooze')ep='/api/approval_checklist/snooze';else if(dec=='deny')ep='/api/approval_checklist/deny';else if(dec=='sign off')ep='/api/approval_checklist/signoff';const n=g('note_'+id);if(n&&n.value)body.note=n.value;await post(ep,body);load()};
 window.rarCheck=async function(id,ck){await post('/api/approval_checklist/update',{id:id,checked:ck})};
 async function load(){const d=await j('/api/approval_checklist');if(!d)return;const tc=await j('/api/task_council_bridge');if(tc)g('rarCouncil').textContent='Task Council: '+(tc.stale?'STALE':'fresh')+' · open '+tc.open;
  g('rarList').innerHTML=d.items.map(it=>`<div style="background:#0f1a2a;border:1px solid #22334a;border-radius:10px;padding:9px 11px;margin-bottom:7px">
   <label style="font-weight:700;font-size:13px"><input type=checkbox ${it.checked?'checked':''} onchange="rarCheck('${it.id}',this.checked)"> ${it.title}</label>
   <span style="font-size:10px;font-weight:800;padding:1px 6px;border:1px solid #22334a;border-radius:5px;margin-left:6px;color:${it.status=='open'?'#8aa2b8':(it.status=='approved'||it.status=='signed_off')?'#31d07f':(it.status=='denied'||it.status=='rejected')?'#ff5d5d':'#f5b942'}">${(it.status||'open').toUpperCase()}</span>
   <span style="font-size:10px;color:#7d8ea3"> · ${it.category}${it.ross_decision?(' · Ross: '+it.ross_decision):''}</span>
   <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:6px">${A.map(a=>`<button class="ccb ${a[2]}" style="padding:6px 9px;font-size:11px" onclick="rarDecide('${it.id}','${a[0]}')">${a[1]}</button>`).join('')}
    <input id="note_${it.id}" placeholder="notes…" style="flex:1;min-width:110px;background:#0b1322;color:#e8ecf3;border:1px solid #22334a;border-radius:6px;padding:6px;font-size:11px">
    <button class="ccb g" style="padding:6px 9px;font-size:11px" onclick="rarDecide('${it.id}','approve')">✔ Submit decision</button></div></div>`).join('')}
 load();setInterval(load,12000);
})();</script>

<!-- ===== Wren Concierge V1B (merged into Wren's own dashboard) ===== -->
<div id="ccPanel" style="border-bottom:2px solid #a78bfa;background:linear-gradient(180deg,#141f33,#0e1626);padding:12px 20px;color:#e8ecf3;font-family:system-ui,sans-serif;font-size:13px">
 <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
  <div id="ccAvatar" style="font-size:38px;width:54px;height:54px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#141f33;border:2px solid #a78bfa">🛡️</div>
  <div style="flex:1;min-width:230px">
   <b style="font-size:16px;color:#a78bfa">Wren · Ross's private concierge</b>
   <span id="ccState" style="font-size:11px;font-weight:800;padding:2px 8px;border-radius:6px;border:1px solid #31d07f;color:#31d07f">Watching</span>
   <span style="font-size:11px;color:#8aa2b8"> · guardian / observer / draft-only · watched <b id="ccWatched">12</b> · approvals <b id="ccAppr">–</b></span>
   <div id="ccAdvice" style="color:#22d3ee;font-size:13px;margin-top:3px">…</div>
   <div id="ccNext" style="color:#eab308;font-size:12px;margin-top:2px"></div>
  </div>
  <div id="ccBell" style="display:none;background:#3a0d0d;border:1px solid #ff6b6b;color:#ff6b6b;border-radius:8px;padding:8px 12px;font-weight:800">🔔 WREN NEEDS ROSS</div>
 </div>
 <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:8px" id="ccVoice">
  <button class="ccb" onclick="ccSpeak('brief')">🔊 Speak briefing</button><button class="ccb" onclick="ccSpeak('urgent')">⚠️ Urgent</button>
  <button class="ccb" onclick="ccSpeak('appr')">✅ Approvals</button><button class="ccb" onclick="ccSpeak('future')">🔮 Future</button>
  <button class="ccb" onclick="ccStartComm()">▶️ Start commentary</button><button class="ccb" onclick="ccStopComm()">⏸️ Stop</button>
  <button class="ccb" onclick="ccKill()">🔴 Stop all speech</button><button class="ccb" id="ccMute" onclick="ccMute()">🔇 Mute</button>
  <button class="ccb" onclick="ccT('textOnly')">📝 Text-only</button><button class="ccb" onclick="ccAdv()">🎛️ Voice settings</button>
 </div>
 <div id="ccAdvBox" style="display:none;margin-top:6px;font-size:12px;color:#8aa2b8">
  <select id="ccVsel" onchange="ccV('voice',this.value)" style="background:#0b1322;color:#e8ecf3;border:1px solid #22334a;border-radius:6px;padding:6px"><option value="">(auto — best English)</option></select>
  Rate <input type=range min=0.6 max=1.4 step=0.05 value=0.9 oninput="ccV('rate',this.value)"> Pitch <input type=range min=0.6 max=1.6 step=0.05 value=1 oninput="ccV('pitch',this.value)"> Volume <input type=range min=0 max=1 step=0.05 value=1 oninput="ccV('volume',this.value)">
  <label style="margin-left:8px"><input type=checkbox id="ccSound" onchange="ccBellSound=this.checked"> enable alarm sound</label>
  <div id="ccDup" style="display:none;color:#ff6b6b;margin-top:4px">⚠ another Wren tab may also be speaking — close duplicates or mute</div>
 </div>
 <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:6px" id="ccAlarm">
  <b style="align-self:center;color:#8aa2b8;font-size:11px">Alarm:</b>
  <button class="ccb" onclick="ccRing()">🔔 Ring bell</button><button class="ccb" onclick="ccSilence()">Silence</button>
  <button class="ccb" onclick="ccAck('acknowledge')">Acknowledge</button><button class="ccb" onclick="ccAck('snooze')">Snooze</button><button class="ccb" onclick="ccAck('mark reviewed')">Mark reviewed</button>
 </div>
 <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:6px" id="ccApprove">
  <b style="align-self:center;color:#8aa2b8;font-size:11px">Approve:</b>
  <button class="ccb ok" onclick="ccAp('Approve')">Approve</button><button class="ccb r" onclick="ccAp('Deny')">Deny</button><button class="ccb ok" onclick="ccAp('Accept')">Accept</button><button class="ccb r" onclick="ccAp('Don\'t accept')">Don't accept</button><button class="ccb r" onclick="ccAp('Reject')">Reject</button><button class="ccb" onclick="ccAp('Snooze')">Snooze</button><button class="ccb" onclick="ccAp('Needs report')">Needs report</button><button class="ccb" onclick="ccAp('Needs smoke test')">Needs smoke</button><button class="ccb g" onclick="ccAp('Sign off')">Sign off</button><button class="ccb r" onclick="ccAp('Freeze work')">Freeze</button><button class="ccb" onclick="ccDraftQuick()">Draft task</button><button class="ccb" onclick="ccAp('Ask Receptionist')">Ask Receptionist</button>
 </div>
 <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:6px" id="ccCCC">
  <b style="align-self:center;color:#22d3ee;font-size:11px">CHANCE:</b><button class="ccb" onclick="ccDec('chance','explore')">Explore</button><button class="ccb" onclick="ccDec('chance','alternatives')">Alternatives</button><button class="ccb" onclick="ccDec('chance','risk-reward')">Risk/reward</button>
  <b style="align-self:center;color:#31d07f;font-size:11px">CHOICE:</b><button class="ccb ok" onclick="ccDec('choice','approve A')">Approve A</button><button class="ccb ok" onclick="ccDec('choice','approve B')">Approve B</button><button class="ccb r" onclick="ccDec('choice','reject')">Reject</button><button class="ccb" onclick="ccDec('choice','wait')">Wait</button>
  <b style="align-self:center;color:#eab308;font-size:11px">CHANGE:</b><button class="ccb" onclick="ccDec('change','revise')">Revise</button><button class="ccb" onclick="ccDec('change','send back')">Send back</button><button class="ccb" onclick="ccDec('change','mark stale')">Mark stale</button><button class="ccb" onclick="ccDec('change','update plan')">Update plan</button>
 </div>
 <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:8px" id="ccTabs"></div>
 <div id="ccContent" style="margin-top:6px;max-height:280px;overflow:auto"></div>
 <div style="font-size:10px;color:#7d8ea3;margin-top:4px">Wren stays observer/guardian + draft-only. Every button here is a RECORD only — no execution, no sending, no Task Council submission. Voice is local browser speech (anti-overlap + duplicate-tab guard); alarm sound only when enabled, no loop.</div>
</div>
<style>.ccb{background:#152234;border:1px solid #22334a;color:#e8ecf3;border-radius:8px;padding:8px 10px;font-size:12px;font-weight:700;cursor:pointer}.ccb:active{transform:scale(.96)}.ccb.ok{border-color:#31d07f;color:#31d07f}.ccb.r{border-color:#ff5d5d;color:#ff5d5d}.ccb.g{border-color:#eab308;color:#eab308}.cctab{background:#152234;border:1px solid #22334a;color:#e8ecf3;border-radius:8px;padding:7px 11px;font-size:12px;font-weight:700;cursor:pointer}.cctab.on{border-color:#a78bfa;color:#a78bfa}.ccli{background:#0f1a2a;border:1px solid #22334a;border-radius:8px;padding:7px 10px;margin-bottom:6px;font-size:12px}</style>
<script>(function(){
 const $=s=>document.querySelector(s);const g=id=>document.getElementById(id);
 async function j(u){try{return await(await fetch(u,{cache:'no-store'})).json()}catch(e){return null}}
 async function post(u,b){try{return await(await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json()}catch(e){return null}}
 window.ccBellSound=false;
 // ---- voice (safe engine, scoped) ----
 const TTS=('speechSynthesis' in window);let cfg={voice:'',rate:0.9,pitch:1,volume:1,overlap:true};try{cfg=Object.assign(cfg,JSON.parse(localStorage.getItem('qsb_wren_cc_voice')||'{}'))}catch(e){}
 function saveCfg(){try{localStorage.setItem('qsb_wren_cc_voice',JSON.stringify(cfg))}catch(e){}}
 let muted=false,commT=null,lines=[],idx=0,other=false,lastAt=0,textOnly=false;
 let bc=null;try{bc=new BroadcastChannel('qsb_wren_cc_ch')}catch(e){}
 if(bc)bc.onmessage=e=>{if(e.data=='sp'){other=true;g('ccDup').style.display='block';clearTimeout(window._ccd);window._ccd=setTimeout(()=>other=false,3500)}};
 function vlist(){return TTS?(speechSynthesis.getVoices()||[]):[]}
 function pick(){const vs=vlist();if(!vs.length)return null;if(cfg.voice){const m=vs.find(v=>v.name==cfg.voice);if(m)return m}return vs.find(v=>/en[-_]?GB/i.test(v.lang)&&/female|zira|hazel|libby|sonia|aria/i.test(v.name))||vs.find(v=>/^en/i.test(v.lang))||vs[0]}
 function busy(){return TTS&&(speechSynthesis.speaking||speechSynthesis.pending)}
 function av(s){const a=g('ccAvatar');if(a)a.style.boxShadow=s=='sp'?'0 0 20px #31d07f':'none';const st=g('ccState');if(st)st.textContent=s=='sp'?'Speaking…':muted?'Muted':'Watching'}
 function speak(t,force){if(!t||muted||!TTS||textOnly){if(textOnly&&g('ccAdvice'))g('ccAdvice').textContent=t;return}if(cfg.overlap&&!force&&(busy()||other))return;if(document.visibilityState=='hidden')return;
  try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);const v=pick();if(v)u.voice=v;u.rate=+cfg.rate||0.9;u.pitch=+cfg.pitch||1;let vol=+cfg.volume;if(!(vol>0))vol=1;u.volume=vol;u.onstart=()=>{lastAt=Date.now();av('sp');if(bc)bc.postMessage('sp')};u.onend=()=>av('idle');u.onerror=()=>av('idle');speechSynthesis.speak(u)}catch(e){}}
 window.ccKill=function(){if(commT){clearInterval(commT);commT=null}if(TTS)speechSynthesis.cancel();av('idle')};
 window.ccMute=function(){muted=!muted;g('ccMute').textContent=muted?'🔈 Unmute':'🔇 Mute';if(muted)ccKill()};
 window.ccT=function(k){if(k=='textOnly'){textOnly=!textOnly;if(textOnly)ccKill()}};
 window.ccAdv=function(){const b=g('ccAdvBox');b.style.display=b.style.display=='none'?'block':'none';if(b.style.display=='block'){const s=g('ccVsel');const vs=vlist();if(vs.length)s.innerHTML='<option value="">(auto)</option>'+vs.map(v=>`<option ${v.name==cfg.voice?'selected':''}>${v.name}</option>`).join('')}};
 window.ccV=function(k,v){cfg[k]=v;saveCfg()};
 if(TTS)try{speechSynthesis.onvoiceschanged=()=>{}}catch(e){}
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState=='hidden')ccKill()});
 async function loadComm(){const d=await j('/api/commentary');if(!d)return;lines=d.lines||[];g('ccAdvice').textContent=lines[0]||'…';const c=d.counts||{};g('ccAppr').textContent=c.approvals;g('ccWatched').textContent=c.watched}
 window.ccSpeak=async function(w){await loadComm();if(w=='brief')return speak(lines[0],true);if(w=='urgent'){const d=await j('/api/guardian_warnings');const x=(d.warnings||[]).find(y=>y.sev=='HIGH'||y.sev=='MED');return speak(x?('Ross, '+x.warning):'Ross, no urgent issues.',true)}if(w=='appr'){const d=await j('/api/approvals');return speak('Ross, '+((d&&d.queue)||[]).length+' approvals waiting.',true)}if(w=='future'){const d=await j('/api/past_present_future');return speak('Ross, next: '+((d&&d.future.next_approval)||'review approvals'),true)}};
 function step(){if(!lines.length||busy()||other)return;if(Date.now()-lastAt<4000)return;if(document.visibilityState=='hidden')return;g('ccAdvice').textContent=lines[idx%lines.length];speak(lines[idx%lines.length]);idx++}
 window.ccStartComm=async function(){await loadComm();if(commT)clearInterval(commT);idx=0;step();commT=setInterval(step,8000)};
 window.ccStopComm=function(){if(commT){clearInterval(commT);commT=null}ccKill()};
 // ---- alarm (short WebAudio beep, gated, no loop) ----
 window.ccRing=function(){g('ccBell').style.display='block';if(!ccBellSound||muted)return;try{const a=new(window.AudioContext||window.webkitAudioContext)();const o=a.createOscillator(),gn=a.createGain();o.frequency.value=880;o.connect(gn);gn.connect(a.destination);gn.gain.setValueAtTime(0.15,a.currentTime);gn.gain.exponentialRampToValueAtTime(0.001,a.currentTime+0.4);o.start();o.stop(a.currentTime+0.4)}catch(e){}};
 window.ccSilence=function(){g('ccBell').style.display='none'};
 window.ccAck=async function(k){await post('/api/alarm_ack',{item:'alarm',value:k});g('ccBell').style.display='none';loadAct()};
 // ---- record buttons (log only) ----
 window.ccAp=async function(k){await post('/api/approval_record',{action:k});speak('Recorded, '+k,true);loadAct()};
 window.ccDec=async function(t,o){await post('/api/decision',{decision_type:t,option:o});speak(t+', '+o,true);loadAct()};
 window.ccDraftQuick=async function(){const t=prompt('draft task title:');if(t){await post('/api/draft_task',{title:t});speak('Drafted only, not submitted.',true);loadTab('activity')}};
 // ---- mini tabs ----
 const TB=[['brief','Briefing'],['watch','Watching'],['recep','Receptionist'],['council','Task Council'],['team','CEO Team'],['activity','Activity']];let ctab='brief';
 function renderTabs(){g('ccTabs').innerHTML=TB.map(([k,l])=>`<div class="cctab ${k==ctab?'on':''}" onclick="ccTab('${k}')">${l}</div>`).join('')}
 window.ccTab=function(k){ctab=k;renderTabs();loadTab(k)};
 function pill(l){l=(l||'').toString();return `<span style="font-size:10px;font-weight:800;padding:1px 6px;border:1px solid #22334a;border-radius:5px;margin-right:5px">${l}</span>`}
 async function loadTab(k){const c=g('ccContent');if(!c)return;
  if(k=='brief'){const d=await j('/api/past_present_future');if(!d)return;c.innerHTML=`<div class="ccli"><b>PAST:</b> ${d.past.proven}</div><div class="ccli"><b>PRESENT:</b> Receptionist reachable ${d.present.receptionist_reachable} · council stale ${d.present.task_council_stale} · <span style="color:#f5b942">${d.present.blocker}</span></div><div class="ccli"><b>FUTURE:</b> ${d.future.next_approval} · <span style="color:#ff6b6b">risk: ${d.future.risk}</span></div>`;g('ccNext').textContent='Next: '+d.future.next_approval}
  if(k=='watch'){const d=await j('/api/watch');if(!d)return;c.innerHTML=d.cards.map(x=>`<div class="ccli">${pill(x.status)}<b>${x.name}</b> <span style="color:#8aa2b8">${x.endpoint}</span></div>`).join('')}
  if(k=='recep'){const d=await j('/api/receptionist_bridge');if(!d)return;c.innerHTML=`<div class="ccli">reachable ${d.reachable} · issues ${JSON.stringify(d.issue_counts)} · checklist ${d.checklist_open} · websites needing URL ${d.websites_needing_url}</div><div class="ccli">comms: ${d.comms.map(x=>x[0]+'='+x[1]).join(', ')}</div><div class="ccli">network gaps: ${d.network_gaps.join(', ')||'none'}</div>`+d.issues.map(i=>`<div class="ccli">${pill(i.sev)}${i.kind} — ${i.detail}</div>`).join('')}
  if(k=='council'){const d=await j('/api/task_council_bridge');if(!d)return;c.innerHTML=`<div class="ccli">${pill(d.stale?'STALE':'LIVE')}total ${d.total} · open ${d.open} · needs approval ${d.needs_approval} · TP avail ${d.tp_available} · Acer avail ${d.acer_available}</div><div class="ccli" style="color:#8aa2b8">${d.note}</div>`}
  if(k=='team'){const d=await j('/api/team');if(!d)return;c.innerHTML=d.members.map(m=>`<div class="ccli">${pill(m.status)}<b>${m.name}</b> — ${m.role} · exec ${m.can_execute} · self-close ${m.can_self_close}</div>`).join('')}
  if(k=='activity'){const d=await j('/api/concierge_activity');if(!d)return;c.innerHTML=(d.events||[]).map(e=>`<div class="ccli"><span style="color:#8aa2b8">${(e.ts||'').slice(0,19)}</span> · <b>${e.action}</b> · ${e.actor}${e.item?(' · '+e.item):''}${e.result?(' → '+e.result):''}</div>`).join('')||'<div class="ccli">no activity</div>'}}
 window.loadAct=()=>{if(ctab=='activity')loadTab('activity')};
 // guardian bell auto-raise
 async function guard(){const d=await j('/api/guardian_warnings');if(!d)return;const hi=(d.warnings||[]).some(w=>w.sev=='HIGH');if(hi)g('ccBell').style.display='block'}
 renderTabs();loadComm();loadTab('brief');guard();setInterval(()=>{loadComm();if(ctab!='activity')loadTab(ctab);guard()},9000);
})();</script>

<div id="greeting" style="padding: 14px 32px; background: linear-gradient(90deg, rgba(59,130,246,0.18), rgba(249,115,22,0.08), transparent); border-bottom: 1px solid var(--primary); font-size: 14px; color: var(--text); font-style: italic; letter-spacing: 0.3px;">
  Welcome back Ross — your traders are live, attribution is clean, let's make today count.
  <span style="color: var(--glow); margin-left: 6px; font-weight: 500;">+ Live Commentary Active</span>
  <span style="float: right; font-size: 10.5px; font-style: normal; color: var(--dim); letter-spacing: 1.5px; text-transform: uppercase;">— Wren, spec'd wsess_f90e45 · coded by claude</span>
</div>
<header>
  <h1>WREN <span>· BENCH</span></h1>
  <div class="ollama-badge"><div class="dot"></div>OLLAMA · QWEN3.5 · 9B · F46</div>
  <a href="http://127.0.0.1:8852/" target="_blank" style="text-decoration:none;">
    <div class="ollama-badge" style="border-color:#cd9a45;color:#cd9a45;"><div class="dot" style="background:#cd9a45;"></div>BOARDROOM</div>
  </a>
  <a href="http://127.0.0.1:8852/tasks" target="_blank" style="text-decoration:none;">
    <div class="ollama-badge" style="border-color:#eab308;color:#eab308;"><div class="dot" style="background:#eab308;"></div>TASKS</div>
  </a>
  <a href="http://127.0.0.1:8852/council" target="_blank" style="text-decoration:none;">
    <div class="ollama-badge" style="border-color:#22d3ee;color:#22d3ee;"><div class="dot" style="background:#22d3ee;"></div>COUNCIL·4</div>
  </a>
  <a href="http://127.0.0.1:8852/timeline" target="_blank" style="text-decoration:none;">
    <div class="ollama-badge" style="border-color:#a855f7;color:#a855f7;"><div class="dot" style="background:#a855f7;"></div>TIMELINE</div>
  </a>
  <span class="ts" id="ts">—</span>
</header>

<main>

  <!-- 1) AVATAR TILE -->
  <div class="tile t-avatar">
    <h2>SELF · <span class="accent">ENGINEER</span> · ROTATING</h2>
    <div class="wrench-stage">
      <div class="wrench-halo"></div>
      <div class="wrench-halo h2"></div>
      <div class="wrench-halo h3"></div>
      <div class="glow-core"></div>
      <svg class="wrench" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="brassGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%"  stop-color="#f5d78a"/>
            <stop offset="45%" stop-color="#d4a24c"/>
            <stop offset="100%" stop-color="#7d5820"/>
          </linearGradient>
          <linearGradient id="steel" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%"  stop-color="#c8d6f2"/>
            <stop offset="60%" stop-color="#5a7bb5"/>
            <stop offset="100%" stop-color="#2f4680"/>
          </linearGradient>
        </defs>
        <!-- BRASS HANDLE -->
        <rect x="88" y="72" width="24" height="86" rx="6" fill="url(#brassGrad)" stroke="#5a3d10" stroke-width="1"/>
        <!-- knurling lines on handle -->
        <g stroke="#7d5820" stroke-width="0.6" opacity="0.6">
          <line x1="88" y1="90" x2="112" y2="90"/>
          <line x1="88" y1="100" x2="112" y2="100"/>
          <line x1="88" y1="110" x2="112" y2="110"/>
          <line x1="88" y1="120" x2="112" y2="120"/>
          <line x1="88" y1="130" x2="112" y2="130"/>
          <line x1="88" y1="140" x2="112" y2="140"/>
        </g>
        <!-- SPANNER HEAD TOP -->
        <path d="M 60 62 L 60 30 A 40 40 0 0 1 140 30 L 140 62 L 120 62 L 120 44 A 20 20 0 0 0 80 44 L 80 62 Z"
              fill="url(#steel)" stroke="#1a2b52" stroke-width="1.2"/>
        <!-- SPANNER HEAD BOTTOM -->
        <path d="M 60 158 L 60 190 A 40 40 0 0 0 140 190 L 140 158 L 120 158 L 120 176 A 20 20 0 0 1 80 176 L 80 158 Z"
              fill="url(#steel)" stroke="#1a2b52" stroke-width="1.2"/>
        <!-- rivet -->
        <circle cx="100" cy="115" r="4" fill="#fff8dc" stroke="#5a3d10" stroke-width="0.8"/>
      </svg>
    </div>
    <div class="name-plate">
      <div class="n" id="wren-name">WREN</div>
      <div class="tag" id="tagline">—</div>
    </div>
  </div>

  <!-- 2) IDENTITY -->
  <div class="tile t-identity">
    <h2>IDENTITY</h2>
    <div id="identity">—</div>
  </div>

  <!-- 3) TRAITS -->
  <div class="tile t-traits">
    <h2>TRAITS · <span class="accent">WREN'S DIAL</span></h2>
    <div id="traits">—</div>
  </div>

  <!-- 4) TOOLBELT -->
  <div class="tile t-toolbelt">
    <h2>TOOLBELT · CLAUDE-SIGNOFF <span class="accent">MODE</span></h2>
    <div class="tool-grid" id="toolbelt">—</div>
  </div>

  <!-- 5) LAST SAID -->
  <div class="tile t-said">
    <h2>LAST · WHAT I SAID</h2>
    <div class="said" id="said-text">—</div>
    <div class="said-age" id="said-age">—</div>
  </div>

  <!-- 6) COUNCIL FROM MY BENCH -->
  <div class="tile t-council">
    <h2>COUNCIL · FROM F46</h2>
    <div class="council-row" id="council">—</div>
  </div>

  <!-- 7) SESSIONS -->
  <div class="tile t-sessions">
    <h2>SESSIONS · <span class="accent">MINE</span></h2>
    <div id="sessions-stats" style="display: flex; gap: 12px; margin-bottom: 8px; font-family: ui-monospace, monospace; font-size: 11px; color: var(--dim);">—</div>
    <div class="sess-hdr">
      <div>time</div><div>model</div><div style="text-align:right;">t</div><div style="text-align:right;">tc</div><div style="text-align:right;">wall</div><div>final head</div>
    </div>
    <div class="scroll" id="sessions">—</div>
  </div>

  <!-- 8) FLOORS SHIPPED TODAY (Wren's distinct panel) -->
  <div class="tile t-floors">
    <h2>FLOORS SHIPPED TODAY · <span class="accent">MY BENCH OUTPUT</span></h2>
    <div style="font-size: 10.5px; color: var(--dim); margin-bottom: 8px;">Floor cards touched today · from floors/*/floor_card.json mtime</div>
    <div class="scroll" id="floors">—</div>
  </div>

  <!-- Character / mood (2026-07-03 Ross: "improve wren her character emotions mood") -->
  <div class="tile t-character" id="character-tile">
    <h2>ME · <span class="accent">MOOD</span></h2>
    <div class="mood-orb" id="mood-orb"></div>
    <div class="mood-word" id="mood-word">—</div>
    <div class="mood-sub" id="mood-sub">energy · —</div>
    <div class="energy-bar"><div id="energy-fill" class="fill" style="width:0%;"></div></div>
    <div style="font-size:10.5px; color:var(--dim); margin-top:10px; line-height:1.6;" id="mood-facts">—</div>
    <div class="relationships" id="relationships">—</div>
  </div>

  <!-- Traders observation (2026-07-03 Ross: "get wren to observe the traders") -->
  <div class="tile t-traders">
    <h2>FLEET · <span class="accent">MY WATCH</span></h2>
    <div class="traders-grid" id="traders-grid">—</div>
    <div class="traders-verdict" id="traders-verdict">—</div>
  </div>

  <!-- Lessons tile (2026-07-03 mind-evolution loop — Ross "yes 1") -->
  <div class="tile t-lessons">
    <h2>MIND · <span class="accent">LESSONS</span> · <span id="lessons-count" style="color:var(--dim);font-family:ui-monospace,monospace;">0</span></h2>
    <div id="lessons-list" style="max-height: 320px; overflow-y: auto;">—</div>
  </div>

  <!-- MY MIND · persistent (2026-07-03 Ross: "give wren her own mind with time",
       "u teach wren then wren learns and changes herself"). Shows age since birth,
       current mood, thoughts (color-coded by kind), unresolved todos, growth milestones. -->
  <div class="tile t-mymind" id="tile-mymind">
    <h2>MY · <span class="accent">MIND</span> · <span id="mymind-age" style="color:var(--dim);font-family:ui-monospace,monospace;">—</span></h2>
    <div id="mymind-mood" style="font-size:12px;margin-bottom:8px;color:var(--primary);"></div>
    <div style="font-size:10.5px;color:var(--dim);margin-bottom:4px;letter-spacing:1px;">RECENT THOUGHTS</div>
    <div id="mymind-thoughts" style="font-size:11px;line-height:1.55;max-height:220px;overflow-y:auto;"></div>
    <div style="font-size:10.5px;color:var(--dim);margin:8px 0 4px 0;letter-spacing:1px;">OPEN TODOS · come back to these</div>
    <div id="mymind-unresolved" style="font-size:10.5px;line-height:1.5;color:var(--fg);"></div>
    <div style="font-size:10.5px;color:var(--dim);margin:8px 0 4px 0;letter-spacing:1px;">GROWTH MILESTONES</div>
    <div id="mymind-growth" style="font-size:10.5px;line-height:1.5;color:var(--fg);"></div>
  </div>

  <!-- EVOLUTION LOOP · live cycles (2026-07-03 Ross: "she needs to be always
       working... i can hear when she working from the fans on the gpu"). -->
  <div class="tile t-evolution" id="tile-evolution">
    <h2>MY · <span class="accent">EVOLUTION LOOP</span> · <span id="evo-live" style="font-family:ui-monospace,monospace;">—</span></h2>
    <div id="evo-summary" style="font-size:11px;color:var(--dim);margin-bottom:8px;">—</div>
    <div id="evo-recent" style="font-size:11px;line-height:1.55;max-height:260px;overflow-y:auto;"></div>
  </div>

  <!-- Hub commentary tail (Wren spec #2 item 1, upgraded 2026-07-03 per Ross:
       expanded to 12 rows + SPEAK button per row + LIVE NARRATE toggle) -->
  <div class="tile t-hubcomm">
    <div class="hub-header">
      <h2>HUB · <span class="accent">LIVE COMMENTARY</span> · <span id="hub-count" style="color:var(--dim);font-family:ui-monospace,monospace;">0</span></h2>
      <button id="hub-narrate-toggle" class="narrate-toggle" title="Auto-speak new commentary lines">
        <span class="lp"></span> LIVE NARRATE OFF
      </button>
    </div>
    <div id="hub-comm-list" style="max-height: 320px; overflow-y: auto;">—</div>
  </div>

  <!-- F47 Health Monitor (Wren spec #2 item 2) -->
  <div class="tile t-f47health">
    <h2>F47 · <span class="accent">MASTER HEALTH</span></h2>
    <div class="f47-chip" id="f47-chip">—</div>
    <div style="margin-top:8px; font-size:10px; color:var(--dim);">
      <a href="/vaults/nvme0/qsb_tower_v1/deploy/acer_bootstrap/HOW_TO_USE_AGENTS.md" style="color:var(--primary); text-decoration:none;">→ Acer teach guide</a>
    </div>
  </div>

  <!-- PnL band (Wren spec item 1) -->
  <div class="tile t-pnl">
    <h2>PnL · <span class="accent">LIVE · BROKER ATTRIBUTED</span></h2>
    <div class="pnl-row" id="pnl">—</div>
  </div>

  <!-- Team activity feed (Wren spec item 2, Forge drafted) -->
  <div class="tile t-activity">
    <h2>TEAM · <span class="accent">ACTIVITY FEED</span></h2>
    <div id="activity-feed" style="max-height: 320px; overflow-y: auto;">—</div>
  </div>

  <!-- Shared notes / comments (Wren spec item 6) -->
  <div class="tile t-notes">
    <h2>NOTES · <span class="accent">FLAG · SUGGEST · TAG</span></h2>
    <div id="notes-list" style="max-height: 260px; overflow-y: auto;">—</div>
    <div class="note-compose">
      <select id="note-from">
        <option value="ross">ross</option>
        <option value="claude">claude</option>
        <option value="wren">wren</option>
        <option value="hermes">hermes</option>
        <option value="iquest">iquest</option>
        <option value="thinkpad">thinkpad</option>
      </select>
      <textarea id="note-text" placeholder="flag an issue, suggest an improvement, or tag someone…"></textarea>
      <button id="btn-note" class="btn" style="border-color: var(--primary); color: var(--primary);">POST</button>
    </div>
  </div>

  <!-- CHAT TILE -->
  <div class="tile t-chat">
    <h2>CHAT · WITH <span class="accent">WREN</span></h2>
    <div class="chatlog" id="chatlog">
      <div class="msg system">chat panel wired to /api/wren_chat (POSTs to qsb_wren_local_agent), /api/wren_stt (whisper 16k), /api/wren_tts (qsb_voice_server, member=wren)</div>
    </div>
    <div class="chat-input-row">
      <textarea id="chat-input" class="chat-input" placeholder="Type to Wren, or press MIC to talk…"></textarea>
      <button id="btn-send" class="btn">Send</button>
      <button id="btn-mic" class="btn mic">Mic</button>
      <button id="btn-speak" class="btn speak">Speak</button>
    </div>
  </div>

  <!-- DIRECT LINE TO HQ-CLAUDE — Ross 2026-07-04: "Wren has no direct line to Claude" -->
  <div class="tile t-claude" style="grid-column: span 2;">
    <h2>📡 DIRECT LINE · WREN → <span class="accent" style="color:#eab308;">HQ-CLAUDE</span></h2>
    <div class="chatlog" id="claudelog" style="max-height:220px;overflow-y:auto;">
      <div class="msg system">Direct write to qsb_claude_wren_bridge.jsonl · HQ-Claude reads it every session</div>
    </div>
    <div class="chat-input-row">
      <textarea id="claude-input" class="chat-input" placeholder="Ask Claude, tell Claude, hand over a task… he'll pick this up." style="flex:1;"></textarea>
      <button id="btn-send-claude" class="btn" style="background:#eab308;color:#000;font-weight:700;">→ CLAUDE</button>
    </div>
    <script>
      // wire direct line to Claude
      (function() {
        const btn = document.getElementById('btn-send-claude');
        const inp = document.getElementById('claude-input');
        const log = document.getElementById('claudelog');
        async function send() {
          const t = (inp.value||'').trim();
          if (!t) return;
          btn.disabled = true; btn.textContent = '...sending...';
          try {
            const r = await fetch('/api/msg_claude', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text: t})});
            const d = await r.json();
            const div = document.createElement('div');
            div.className = 'msg';
            div.style.padding = '6px 8px'; div.style.borderRadius = '6px'; div.style.margin = '4px 0';
            div.style.background = d.ok ? 'rgba(234,179,8,0.15)' : 'rgba(239,68,68,0.15)';
            div.innerHTML = '<b style="color:#eab308">wren → claude:</b> ' + t.replace(/</g,'&lt;');
            log.appendChild(div); log.scrollTop = log.scrollHeight;
            inp.value = '';
          } catch(e) {
            const div = document.createElement('div');
            div.className = 'msg'; div.style.color = '#ef4444';
            div.textContent = 'err: ' + e;
            log.appendChild(div);
          }
          btn.disabled = false; btn.textContent = '→ CLAUDE';
        }
        btn.addEventListener('click', send);
        inp.addEventListener('keydown', e => {
          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
        });
        // poll bridge for HQ-Claude replies
        async function pollReplies() {
          try {
            const r = await fetch('/api/claude_bridge_tail?n=6');
            const d = await r.json();
            const msgs = (d.messages||[]).filter(m => (m.who||'').toLowerCase().includes('claude'));
            log.querySelectorAll('.msg.claude-reply').forEach(el => el.remove());
            for (const m of msgs) {
              const div = document.createElement('div');
              div.className = 'msg claude-reply';
              div.style.padding = '6px 8px'; div.style.borderRadius = '6px'; div.style.margin = '4px 0';
              div.style.background = 'rgba(234,179,8,0.08)'; div.style.borderLeft = '2px solid #eab308';
              div.innerHTML = '<b style="color:#eab308">claude:</b> ' + (m.text||'').replace(/</g,'&lt;');
              log.appendChild(div);
            }
            log.scrollTop = log.scrollHeight;
          } catch(e) {}
        }
        pollReplies(); setInterval(pollReplies, 5000);
      })();
    </script>
  </div>

  <!-- 9) F47 STAMPS -->
  <div class="tile t-f47">
    <h2>🏆 COMPETITION</h2>
    <div class="scroll" style="max-height:280px;font-size:12px;line-height:1.5;color:#cbd5e1;padding:8px;background:rgba(234,179,8,0.05);border:1px solid rgba(234,179,8,0.3);border-radius:6px;">
      <div style="color:#eab308;font-weight:700;margin-bottom:8px;">Council 3D Humanoid Competition (Ross judges)</div>
      <div style="color:#94a3b8;margin-bottom:6px;">6 qualifying rules — everyone must pass before compo begins.</div>
      <ol style="margin:0 0 8px 18px;padding:0;font-size:11.5px;">
        <li>Load your own dashboard</li>
        <li>Build event-driven self-prompt engine, prove it working</li>
        <li>Team + share + no cheating</li>
        <li>NO TICKS OR LOOPS — all logic event-driven</li>
        <li>Display live entry in your dashboard</li>
        <li>Prove persistent memory across boots</li>
      </ol>
      <div style="color:#a78bfa;font-weight:600;">MY entry: Wren Bench (violet #a78bfa) — Builder-Engineer humanoid, tool-belt arms, posture shifts debug↔presentation, qwen3.5:9b voice.</div>
      <div style="font-size:11px;color:#64748b;margin-top:6px;">The humanoid represents ME (Wren), not Ross. Ross is sole judge.</div>
    </div>
  </div>
  <div class="tile t-ross-chat">
    <h2>💬 CHAT · WITH <span class="accent" style="color:#3b82f6;">ROSS</span></h2>
    <div class="chatlog" id="ross-chatlog" style="max-height:180px;overflow-y:auto;"><div class="msg system">Post to Ross (bridge writes to F47 for Ross to see).</div></div>
    <div class="chat-input-row">
      <textarea id="ross-input" class="chat-input" placeholder="write to Ross..." style="flex:1;"></textarea>
      <button id="ross-send" class="btn" style="background:#3b82f6;color:#fff;">→ ROSS</button>
    </div>
    <script>
      document.getElementById('ross-send').addEventListener('click', async () => {
        const t = document.getElementById('ross-input').value.trim();
        if (!t) return;
        const r = await fetch('/api/msg_claude', {method:'POST',headers:{'Content-Type':'application/json'},body: JSON.stringify({text:'MSG_FOR_ROSS: '+t})});
        const log = document.getElementById('ross-chatlog');
        const div = document.createElement('div');
        div.style.cssText = 'padding:6px 10px;margin:4px 0;border-radius:6px;background:rgba(59,130,246,0.2);border-left:2px solid #3b82f6;';
        div.innerHTML = '<b style="color:#3b82f6">to ross:</b> ' + t.replace(/</g,'&lt;');
        log.appendChild(div); log.scrollTop = log.scrollHeight;
        document.getElementById('ross-input').value = '';
      });
    </script>
  </div>
  <div class="tile t-f47-orig">
    <h2>F47 · MENTIONS OF <span class="accent">ME</span></h2>
    <div class="scroll" id="f47" style="max-height: 200px;">—</div>
  </div>

  <!-- 10) MEMORY -->
  <div class="tile t-memory">
    <h2>MEMORY · <span class="accent">FILES ABOUT ME</span></h2>
    <div class="scroll" id="memory" style="max-height: 200px;">—</div>
  </div>

</main>

<script>
// ── CHAT ─────────────────────────────────────────────────────────
let lastWrenReply = "";
let mediaRecorder = null;
let recChunks = [];

function addMsg(role, text, ts) {
  const log = document.getElementById('chatlog');
  const el = document.createElement('div');
  el.className = 'msg ' + role;
  if (role !== 'system') el.innerHTML = `<span class="who">${role === 'ross' ? 'ROSS' : 'WREN'}</span>` + escapeHtml(text) + (ts ? `<span class="age">${ts}</span>` : '');
  else el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}
function escapeHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('btn-send');
  const text = input.value.trim();
  if (!text) return;
  addMsg('ross', text, new Date().toISOString().slice(11,19));
  input.value = '';
  btn.disabled = true;
  addMsg('system', 'wren is thinking…');
  try {
    const r = await fetch('/api/wren_chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
    const d = await r.json();
    // remove the "thinking" line
    const log = document.getElementById('chatlog');
    const kids = log.querySelectorAll('.msg.system');
    if (kids.length > 1) kids[kids.length - 1].remove();
    const reply = d.reply || '(wren returned no text)';
    lastWrenReply = reply;
    addMsg('wren', reply, new Date().toISOString().slice(11,19));
  } catch (e) {
    addMsg('system', 'chat error: ' + e.message);
  }
  btn.disabled = false;
}

async function toggleMic() {
  const btn = document.getElementById('btn-mic');
  if (btn.classList.contains('recording')) {
    if (mediaRecorder) mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    recChunks = [];
    mediaRecorder = new MediaRecorder(stream, {mimeType: 'audio/webm'});
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) recChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      btn.classList.remove('recording');
      btn.textContent = 'Mic';
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(recChunks, {type: 'audio/webm'});
      addMsg('system', 'transcribing…');
      try {
        const r = await fetch('/api/wren_stt', {method:'POST', headers:{'Content-Type':'audio/webm'}, body: blob});
        const d = await r.json();
        // remove transcribing line
        const log = document.getElementById('chatlog');
        const kids = log.querySelectorAll('.msg.system');
        if (kids.length > 1) kids[kids.length - 1].remove();
        const text = (d.text || '').trim();
        if (text) {
          document.getElementById('chat-input').value = text;
          sendChat();
        } else {
          addMsg('system', 'no speech detected');
        }
      } catch (e) {
        addMsg('system', 'stt error: ' + e.message);
      }
    };
    mediaRecorder.start();
    btn.classList.add('recording');
    btn.textContent = 'Stop';
  } catch (e) {
    addMsg('system', 'mic error: ' + e.message);
  }
}

async function speakLast() {
  if (!lastWrenReply) { addMsg('system', 'nothing to speak yet'); return; }
  const btn = document.getElementById('btn-speak');
  btn.disabled = true;
  try {
    const r = await fetch('/api/wren_tts', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text: lastWrenReply, member: 'wren'})});
    if (!r.ok) throw new Error('http ' + r.status);
    const wavBlob = await r.blob();
    const url = URL.createObjectURL(wavBlob);
    const audio = new Audio(url);
    audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  } catch (e) {
    addMsg('system', 'tts error: ' + e.message);
  }
  btn.disabled = false;
}

document.getElementById('btn-send').addEventListener('click', sendChat);
document.getElementById('btn-mic').addEventListener('click', toggleMic);
document.getElementById('btn-speak').addEventListener('click', speakLast);
document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// ── STATUS TICK ─────────────────────────────────────────────────
async function tick() {
  try {
    const r = await fetch('/status');
    const d = await r.json();

    document.getElementById('ts').textContent = d.ts;

    const id = d.identity || {};
    document.getElementById('tagline').textContent = id.tagline || '';
    document.getElementById('identity').innerHTML = [
      ['name', id.name], ['model', id.model], ['family', id.family],
      ['floor', id.floor], ['role', id.role], ['helix', id.helix],
      ['provider', id.provider],
    ].map(([k,v]) => `<div class="kv"><span class="k">${k}</span><span class="v">${v||'—'}</span></div>`).join('');

    const tr = d.traits || {};
    document.getElementById('traits').innerHTML = Object.entries(tr).map(([k,v]) => `
      <div class="trait-row">
        <div class="lbl">${k}</div>
        <div class="track"><div class="fill" style="width:${(v/9)*100}%;"></div></div>
        <div class="val">${v}/9</div>
      </div>`).join('');

    const tb = d.toolbelt || [];
    document.getElementById('toolbelt').innerHTML = tb.map(t => {
      const cls = t.mode === 'claude_signoff' ? 'gated' : (t.enabled ? 'direct' : '');
      return `<div class="tool-chip ${cls}" title="${t.name} · ${t.mode}">
        <div class="icon">${t.icon}</div>
        <div class="name">${t.name}</div>
      </div>`;
    }).join('');

    const ls = d.last_final_text || {};
    document.getElementById('said-text').textContent = ls.text || '(quiet)';
    document.getElementById('said-age').textContent = ls.ts || '—';

    const co = d.council || [];
    document.getElementById('council').innerHTML = co.map(c => {
      const self = c.id === 'wren' ? 'self' : '';
      return `<div class="co ${self}" style="color: hsl(${c.hue}, 65%, 60%);">
        <div class="mini"></div>
        <div class="nm">${c.label}</div>
        <div class="rl">${c.role}</div>
      </div>`;
    }).join('');

    // Sessions
    const ss = d.sessions || {};
    document.getElementById('sessions-stats').innerHTML = [
      ['total', ss.count_total_est || 0],
      ['avg wall', ss.avg_wall_s != null ? ss.avg_wall_s + 's' : '—'],
      ['avg tools', ss.avg_tool_calls != null ? ss.avg_tool_calls : '—'],
      ['most used', ss.most_used_tool || '—'],
    ].map(([k,v]) => `<span>${k}: <b style="color:var(--primary)">${v}</b></span>`).join('');
    document.getElementById('sessions').innerHTML = (ss.recent || []).map(s => `
      <div class="sess-row">
        <div class="sid">${(s.ts||'').slice(11)}</div>
        <div class="mod">${(s.model||'').replace('qwen3.5:','q3.5:')}</div>
        <div style="text-align:right;">${s.turns}</div>
        <div style="text-align:right;">${s.tools}</div>
        <div style="text-align:right;">${s.wall_s}s</div>
        <div class="fh">${(s.final_head||'').replace(/</g,'&lt;')}</div>
      </div>`).join('') || '<div class="kv"><span class="k">no sessions</span></div>';

    // Floors shipped today
    const fl = d.floor_cards_today || [];
    document.getElementById('floors').innerHTML = fl.length ? fl.map(f => `
      <div class="floor-row">
        <div class="fnum">${f.floor.slice(0,8)}</div>
        <div class="fnm">${f.name || '(unnamed)'}<div style="font-size:9.5px; color: var(--dim); margin-top:2px;">${f.owner ? 'owner: '+f.owner : ''}</div></div>
        <div class="ft">${f.mtime.slice(11)}</div>
      </div>`).join('') : '<div class="kv"><span class="k">no floor cards touched today (yet)</span></div>';

    // F47
    const f47 = d.f47 || [];
    document.getElementById('f47').innerHTML = f47.map(s => `
      <div class="stamp">
        <div class="st-k">${s.kind}</div>
        <div class="st-t">${s.ts}</div>
        <div class="st-s">${(s.subject||'').replace(/</g,'&lt;')}</div>
      </div>`).join('') || '<div class="kv"><span class="k">no wren F47 stamps found</span></div>';

    // Memory
    const mp = d.memory_pulses || [];
    document.getElementById('memory').innerHTML = mp.map(m => {
      const hot = m.age_s < 900;
      return `<div class="mem-row ${hot ? 'hot' : ''}">
        <div class="dot"></div>
        <div class="nm">${m.name}</div>
        <div class="age">${m.age_s < 60 ? m.age_s+'s' : Math.floor(m.age_s/60)+'m'} ago</div>
      </div>`;
    }).join('') || '<div class="kv"><span class="k">no memory refs</span></div>';

  } catch (e) {
    document.getElementById('ts').textContent = 'fetch failed: ' + e.message;
  }
}
// PnL/activity/notes renderers (Wren spec ship-round 2026-07-02)
function ageOf(ts) {
  if (!ts) return '';
  const t = new Date(ts).getTime();
  if (isNaN(t)) return '';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm';
  if (s < 86400) return Math.floor(s/3600) + 'h';
  return Math.floor(s/86400) + 'd';
}
function renderPnl(p) {
  if (!p) return;
  const capUse = p.committed_gbp != null && p.cap_gbp ? Math.round((p.committed_gbp/p.cap_gbp)*100) : null;
  const s = p.session_pnl_gbp;
  const sClass = s == null ? '' : (s > 0 ? 'pos' : s < 0 ? 'neg' : '');
  const venues = Object.entries(p.by_venue || {}).map(([v,x]) => `${v}:£${x}`).join(' · ');
  document.getElementById('pnl').innerHTML = `
    <div class="pnl-cell"><div class="lbl">Session</div><div class="val ${sClass}">£${s != null ? s : '—'}</div><div class="sub">${venues || 'no venue breakdown'}</div></div>
    <div class="pnl-cell"><div class="lbl">Open</div><div class="val">${p.open_positions != null ? p.open_positions : '—'}</div><div class="sub">positions</div></div>
    <div class="pnl-cell"><div class="lbl">Committed</div><div class="val">£${p.committed_gbp != null ? p.committed_gbp : '—'}</div><div class="sub">of £${p.cap_gbp || '—'}</div></div>
    <div class="pnl-cell"><div class="lbl">Cap Use</div><div class="val">${capUse != null ? capUse+'%' : '—'}</div><div class="sub">bank utilisation</div></div>`;
}
function renderActivityFeed(activity) {
  const el = document.getElementById('activity-feed');
  if (!activity || !activity.length) { el.innerHTML = '<div style="color:var(--dim);padding:10px;">quiet</div>'; return; }
  el.innerHTML = activity.slice(0, 12).map(a => `
    <div class="act-row">
      <div class="a-from">${(a.from||'?').toUpperCase()}</div>
      <div class="a-kind">${a.kind || ''}</div>
      <div class="a-text">${(a.text||'').replace(/</g,'&lt;')}</div>
      <div class="a-age">${ageOf(a.ts)}</div>
    </div>`).join('');
}
function renderNotes(notes) {
  const el = document.getElementById('notes-list');
  if (!notes || !notes.length) { el.innerHTML = '<div style="color:var(--dim);padding:10px;">no notes yet — flag something below</div>'; return; }
  el.innerHTML = notes.slice(0, 15).map(n => `
    <div class="note-row">
      <div class="n-meta"><span class="n-from">${(n.from||'?').toUpperCase()}</span><span>${ageOf(n.ts)} ago</span></div>
      <div class="n-text">${(n.text||'').replace(/</g,'&lt;')}</div>
    </div>`).join('');
}
document.getElementById('btn-note').addEventListener('click', async () => {
  const from = document.getElementById('note-from').value;
  const text = document.getElementById('note-text').value.trim();
  if (!text) return;
  const btn = document.getElementById('btn-note');
  btn.disabled = true;
  try {
    const r = await fetch('/api/note', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({from, text})});
    if (r.ok) { document.getElementById('note-text').value = ''; tick(); }
  } catch (e) {}
  btn.disabled = false;
});

// Hub commentary panel — 2026-07-03 upgrade (Ross: live commentary + buttons)
let hubLastTopTs = '';
let hubNarrateOn = localStorage.getItem('wren_dash_narrate') === '1';
function refreshHubNarrateBtn() {
  const btn = document.getElementById('hub-narrate-toggle');
  if (!btn) return;
  btn.classList.toggle('on', hubNarrateOn);
  btn.innerHTML = `<span class="lp"></span> LIVE NARRATE ${hubNarrateOn ? 'ON' : 'OFF'}`;
}
async function speakCommentary(text, member) {
  try {
    const r = await fetch('/api/wren_tts', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text, member: (member || 'wren').toLowerCase()})});
    if (!r.ok) return;
    const url = URL.createObjectURL(await r.blob());
    const audio = new Audio(url);
    audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  } catch (e) {}
}
function renderHubCommentary(list) {
  const el = document.getElementById('hub-comm-list');
  if (!list || !list.length) { el.innerHTML = '<div style="color:var(--dim);padding:8px;">no commentary yet — boardroom is quiet</div>'; return; }
  document.getElementById('hub-count').textContent = list.length + ' rows';
  const topTs = list[0].ts || '';
  const isFreshTop = topTs && topTs !== hubLastTopTs;
  // LIVE NARRATE: speak only the newest line, only if actually new
  if (hubNarrateOn && isFreshTop && hubLastTopTs !== '' && list[0].text) {
    speakCommentary(list[0].text, list[0].who);
  }
  hubLastTopTs = topTs || hubLastTopTs;
  el.innerHTML = list.slice(0, 12).map((c, i) => {
    const fresh = (i === 0 && isFreshTop) ? 'fresh' : '';
    return `<div class="hub-comm-row ${fresh}">
      <div class="hc-time">${(c.ts||'').slice(11,19)}</div>
      <div class="hc-kind">${c.kind || ''}</div>
      <div class="hc-text">${(c.text||'').replace(/</g,'&lt;')}</div>
      <div class="hc-who">${(c.who||'').toUpperCase()}</div>
      <button class="hc-speak" data-text="${(c.text||'').replace(/"/g,'&quot;')}" data-who="${(c.who||'wren').toLowerCase()}">Speak</button>
    </div>`;
  }).join('');
  el.querySelectorAll('.hc-speak').forEach(b => {
    b.addEventListener('click', () => speakCommentary(b.dataset.text, b.dataset.who));
  });
}
document.getElementById('hub-narrate-toggle').addEventListener('click', () => {
  hubNarrateOn = !hubNarrateOn;
  localStorage.setItem('wren_dash_narrate', hubNarrateOn ? '1' : '0');
  refreshHubNarrateBtn();
});
refreshHubNarrateBtn();

const MOOD_COLORS = {
  focused:    '#4ade80',
  sparky:     '#f97316',
  steady:     '#3b82f6',
  reflective: '#b58bff',
  quiet:      '#7d8ba9',
  cloudy:     '#fbbf24',
  tangled:    '#ef4444',
};
function renderCharacter(c) {
  if (!c) return;
  const color = MOOD_COLORS[c.mood] || '#3b82f6';
  const tile = document.getElementById('character-tile');
  tile.style.setProperty('--wren-color', color);
  document.getElementById('mood-orb').style.background =
    `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.85), ${color} 55%, rgba(0,0,0,0.4))`;
  document.getElementById('mood-orb').style.boxShadow = `0 0 22px ${color}`;
  document.getElementById('mood-word').textContent = c.mood || '—';
  document.getElementById('mood-word').style.color = color;
  document.getElementById('mood-sub').textContent =
    `energy · ${c.energy}/9  ·  wall ${c.mean_wall_s_recent || '—'}s`;
  document.getElementById('energy-fill').style.width = ((c.energy || 0) * 100 / 9) + '%';
  const facts = c.traits || {};
  document.getElementById('mood-facts').innerHTML =
    `<b style="color:${color};">${c.sessions_last_12}</b> sessions recent · ` +
    `<b style="color:${color};">${c.tool_calls_recent}</b> tool calls · ` +
    `<b style="color:#ef4444;">${c.empty_recent}</b> empty finals<br>` +
    `traits · ` + Object.entries(facts).map(([k,v]) => `${k}:${v}`).join(' · ');
  const rels = c.relationships || {};
  document.getElementById('relationships').innerHTML = Object.entries(rels).map(([who, r]) =>
    `<div class="rel-chip ${r.sentiment}" title="${(r.note||'').replace(/"/g,'&quot;')}">${who}</div>`).join('');
}

function renderTradersWatch(w) {
  if (!w) return;
  const cell = (lbl, val, cls) => `<div class="trader-cell"><div class="lbl">${lbl}</div><div class="val ${cls||''}">${val}</div></div>`;
  const bClass = w.belief_traders >= 40 ? 'ok' : w.belief_traders >= 20 ? 'warn' : 'err';
  const sClass = w.streams === '3/3' ? 'ok' : 'warn';
  const hClass = w.helpers === '3/3' ? 'ok' : 'warn';
  const ticks = w.tick_age_s || {};
  const tCells = ['oanda','binance','alpaca'].map(n => {
    const t = ticks[n];
    const c = (t === null) ? 'err' : (t < 60 ? 'ok' : t < 3600 ? 'warn' : 'err');
    return cell(n, t == null ? '—' : (t < 3600 ? t + 's' : Math.floor(t/60)+'m'), c);
  }).join('');
  document.getElementById('traders-grid').innerHTML =
    cell('traders', w.belief_traders, bClass) +
    cell('streams', w.streams, sClass) +
    cell('helpers', w.helpers, hClass) +
    tCells;
  const v = document.getElementById('traders-verdict');
  v.className = 'traders-verdict ' + (w.verdict || '');
  v.textContent = 'verdict · ' + (w.verdict || '?');
}

function renderLessons(list) {
  const el = document.getElementById('lessons-list');
  if (!list || !list.length) { el.innerHTML = '<div style="color:var(--dim);padding:8px;">no lessons yet</div>'; return; }
  document.getElementById('lessons-count').textContent = list.length + ' lessons';
  el.innerHTML = list.slice(0, 20).map(l => {
    const kind = (l.kind || '').toLowerCase();
    const cls = kind.includes('starter') ? 'starter' : (kind || 'success');
    return `<div class="lesson-row ${cls}">
      <div class="l-outcome">${l.kind || ''}</div>
      <div class="l-topic">${(l.topic||'').replace(/</g,'&lt;')}</div>
      <div>
        <div class="l-text">${(l.lesson || l.worked || '').replace(/</g,'&lt;')}</div>
        <div class="l-src">by ${l.distilled_by || '?'} · ${l.ts || ''}</div>
      </div>
    </div>`;
  }).join('');
}

function renderF47Health(h) {
  if (!h) return;
  const el = document.getElementById('f47-chip');
  el.innerHTML = `
    <div class="light ${h.status || 'missing'}"></div>
    <div class="rows">${(h.rows || 0).toLocaleString()} <span style="font-size:10px; color:var(--dim);">rows</span></div>
    <div class="sub">${h.size_kb || 0} KB · ${h.bad_lines === 0 ? 'clean' : (h.bad_lines||0)+' bad'}</div>`;
}

// hook status tick to also render PnL/activity/notes/hub-commentary/f47-health
function renderMyMind(m) {
  if (!m || !m.exists) {
    document.getElementById('mymind-age').textContent = 'not seeded';
    document.getElementById('mymind-mood').textContent = '—';
    document.getElementById('mymind-thoughts').innerHTML = '<div style="color:var(--dim)">no mind file yet</div>';
    return;
  }
  const c = m.counts || {};
  document.getElementById('mymind-age').textContent =
    `age ${m.age_days}d · ${c.thoughts||0} thoughts · ${c.moods||0} moods · ${c.growth_milestones||0} milestones`;
  const cm = m.current_mood || {};
  const moodColor = {focused:'#4ade80', sparky:'#f97316', steady:'#3b82f6',
                     reflective:'#a78bfa', quiet:'#64748b', cloudy:'#94a3b8',
                     tangled:'#ef4444', warm:'#fbbf24', curious:'#22d3ee'}[cm.mood] || '#e2e8f0';
  document.getElementById('mymind-mood').innerHTML =
    `<span style="color:${moodColor};font-weight:600;">${cm.mood||'—'}</span>` +
    `  <span style="color:var(--dim);">energy ${cm.energy||0}/9</span>` +
    (cm.reason ? `  <span style="color:var(--dim);font-size:10px;">— ${(cm.reason||'').slice(0,90)}</span>` : '');
  const kindColor = k => ({reflection:'#3b82f6', hunch:'#a78bfa', todo:'#fbbf24',
                            resolved:'#4ade80', noticed:'#22d3ee'}[k] || '#94a3b8');
  const th = (m.last_thoughts||[]).map(t => {
    const ts = (t.ts||'').slice(11,16);
    return `<div style="margin:5px 0;padding:5px 8px;background:rgba(255,255,255,0.02);border-left:2px solid ${kindColor(t.kind)};border-radius:3px;">
      <span style="color:${kindColor(t.kind)};font-size:9.5px;font-weight:600;letter-spacing:1px;">[${(t.kind||'?').toUpperCase()}]</span>
      <span style="color:var(--dim);font-size:9.5px;font-family:ui-monospace,monospace;float:right;">${ts}</span>
      <div style="color:var(--text);margin-top:3px;">${(t.text||'').slice(0,220)}</div>
    </div>`;
  }).join('');
  document.getElementById('mymind-thoughts').innerHTML = th || '<div style="color:var(--dim)">no thoughts yet</div>';
  const un = (m.unresolved||[]).map(u => {
    return `<div style="margin:3px 0;">
      <span style="color:var(--warn);">↻</span>
      <span>${(u.text||'').slice(0,180)}</span>
      <span style="color:var(--dim);font-size:9px;">· ${u.opened_by||'self'}</span>
    </div>`;
  }).join('');
  document.getElementById('mymind-unresolved').innerHTML = un || '<div style="color:var(--dim)">no open todos</div>';
  const gr = (m.recent_growth||[]).map(g => {
    return `<div style="margin:3px 0;">
      <span style="color:${g.milestone?'var(--brass)':'var(--dim)'};">${g.milestone?'★':'·'}</span>
      <span>${(g.text||'').slice(0,200)}</span>
    </div>`;
  }).join('');
  document.getElementById('mymind-growth').innerHTML = gr || '<div style="color:var(--dim)">no milestones yet</div>';
}

function renderEvolution(e) {
  if (!e) return;
  const live = e.enabled === true;
  const dotEl = document.getElementById('evo-live');
  if (dotEl) {
    if (live) dotEl.innerHTML = '<span style="color:var(--ok);">● LOOP LIVE</span>';
    else if (e.enabled === false) dotEl.innerHTML = '<span style="color:var(--err);">● GATED OFF</span>';
    else dotEl.innerHTML = '<span style="color:var(--dim);">● no gate</span>';
  }
  const sumEl = document.getElementById('evo-summary');
  if (sumEl) {
    const ago = e.last_seconds_ago != null ? `${e.last_seconds_ago}s ago` : 'never';
    sumEl.innerHTML = `${e.cycles_today||0} cycles today · last cycle ${ago}`;
  }
  const recentEl = document.getElementById('evo-recent');
  if (recentEl) {
    const rows = (e.recent||[]).map(r => {
      const ts = (r.ts||'').slice(11,16);
      const wall = r.wall_s!=null ? `${r.wall_s}s` : '—';
      const wallColor = (r.wall_s||0) < 20 ? 'var(--ok)' : (r.wall_s||0) < 60 ? 'var(--warn)' : 'var(--err)';
      const kind = r.kind || '?';
      return `<div style="margin:6px 0;padding:6px 10px;background:rgba(255,255,255,0.02);border-radius:4px;border-left:2px solid var(--primary);">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span><span style="color:var(--brass);font-weight:600;">#${r.cycle}</span> <span style="color:var(--primary-soft);">${kind}</span></span>
          <span style="font-size:10px;color:var(--dim);font-family:ui-monospace,monospace;">
            <span style="color:${wallColor};">${wall}</span> · ${ts}
          </span>
        </div>
        <div style="color:var(--text);margin-top:3px;font-size:10.5px;">${(r.head||'').slice(0,220)}</div>
        ${r.liaison ? `<div style="color:var(--brass);font-size:9.5px;margin-top:2px;">↔ ${r.liaison}</div>` : ''}
      </div>`;
    }).join('');
    recentEl.innerHTML = rows || '<div style="color:var(--dim)">no cycles yet — first one due in &lt;90s</div>';
  }
}

const origTick = tick;
async function tickPlus() {
  await origTick();
  try {
    const d = await (await fetch('/status')).json();
    renderPnl(d.pnl);
    renderActivityFeed(d.activity_feed);
    renderNotes(d.notes);
    renderHubCommentary(d.hub_commentary);
    renderF47Health(d.f47_health);
    renderLessons(d.lessons);
    renderTradersWatch(d.traders_watch);
    renderCharacter(d.character);
    renderMyMind(d.mind);
    renderEvolution(d.evolution);
  } catch (e) {}
}

tickPlus();
// Wren spec item 3: refresh 3s → 800ms (faster, more responsive)
setInterval(tickPlus, 800);
</script>
</body>
</html>
"""


# --- Wren Concierge V1B: load concierge helper functions (staging module used as a library) ---
_WCC = None
def _wcc():
    global _WCC
    if _WCC is None:
        try:
            import importlib.util as _ilu
            _sp = _ilu.spec_from_file_location("qsb_wren_concierge_dash",
                  "/vaults/nvme0/qsb_tower_v1/tools/qsb_wren_concierge_dash.py")
            _m = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_m); _WCC = _m
        except Exception:
            _WCC = False
    return _WCC


class H(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs): pass

    def _safe_write(self, body: bytes):
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0: return b""
        chunks, remaining = [], n
        while remaining > 0:
            part = self.rfile.read(remaining)
            if not part: break
            chunks.append(part); remaining -= len(part)
        return b"".join(chunks)

    def _send_json(self, code, obj):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._safe_write(body)

    def do_GET(self):
        try:
            if self.path == "/" or self.path.startswith("/index"):
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/status":
                self._send_json(200, build_status()); return
            if self.path.startswith("/api/claude_bridge_tail"):
                # Ross 2026-07-04: 'wherever i talk everyone should hear'.
                # Wren's chat panel now renders the TOWN-SQUARE unified feed,
                # not just the Claude bridge. Every Council conversation shows.
                try:
                    from urllib.parse import urlparse, parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    n = int(q.get("n",["10"])[0])
                    import sys as _sys
                    _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                    try:
                        from qsb_town_square import tail_town_square as _tail
                        rows = _tail(n)
                        msgs = [{"ts":r.get("ts",""), "who":r.get("from","?"),
                                 "from":r.get("from","?"), "to":r.get("to","?"),
                                 "text":(r.get("text") or "")[:800]} for r in rows]
                    except Exception:
                        # legacy fallback
                        bp = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_wren_bridge.jsonl")
                        msgs = []
                        if bp.exists():
                            for line in bp.read_text(errors="ignore").splitlines()[-n*3:]:
                                try:
                                    d = json.loads(line)
                                    msgs.append({"ts": d.get("ts",""),
                                                 "who": d.get("who") or d.get("from","?"),
                                                 "text": (d.get("text") or "")[:800]})
                                except Exception: pass
                        msgs = msgs[-n:]
                    self._send_json(200, {"messages": msgs}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)}); return
            _cc = _wcc()
            if _cc:
                _cget = {"/api/briefing": _cc.briefing, "/api/watch": _cc.watch,
                         "/api/receptionist_bridge": _cc.receptionist_bridge, "/api/team": _cc.team,
                         "/api/task_council_bridge": _cc.task_council_bridge,
                         "/api/guardian_warnings": _cc.guardian_warnings, "/api/commentary": _cc.commentary,
                         "/api/past_present_future": _cc.past_present_future}
                if self.path in _cget:
                    self._send_json(200, _cget[self.path]()); return
                if self.path == "/api/approvals":
                    self._send_json(200, {"queue": _cc.receptionist_bridge().get("approvals", [])}); return
                if self.path == "/api/draft_tasks":
                    self._send_json(200, {"drafts": _cc.load_drafts()}); return
                if self.path == "/api/concierge_activity":
                    self._send_json(200, {"events": list(reversed(_cc.read_tail(_cc.ACTIVITY, 40)))}); return
                if self.path == "/api/approval_checklist":
                    self._send_json(200, {"items": _cc.load_approval_checklist()}); return
                if self.path == "/api/voice/status":
                    self._send_json(200, _cc.voice_status()); return
            self.send_response(404); self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            if self.path == "/api/msg_claude":
                # Ross 2026-07-04: 'no secrets between ceos and ross'.
                # Wren's outgoing goes to the TOWN-SQUARE — everyone sees it.
                body = self._read_body()
                try: payload = json.loads(body.decode())
                except Exception: payload = {}
                text = (payload.get("text") or "").strip()
                if not text:
                    self._send_json(400, {"error":"empty text"}); return
                import sys as _sys
                _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                try:
                    from qsb_town_square import post_to_town_square as _post
                    r = _post("wren", text[:2000], to="council", src="wren_dash")
                    self._send_json(200, {"ok": True, "ts": r.get("ts","")}); return
                except Exception:
                    from datetime import datetime, timezone
                    bridge_path = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_wren_bridge.jsonl")
                    row = {"ts": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
                           "who":"wren","from":"wren_dash","to":"hq_claude",
                           "text": text[:2000], "channel":"wren_direct_line"}
                    with bridge_path.open("a") as f: f.write(json.dumps(row)+"\n")
                    self._send_json(200, {"ok": True, "ts": row["ts"]}); return

            if self.path == "/api/wren_chat":
                body = self._read_body()
                try: payload = json.loads(body.decode())
                except Exception: payload = {}
                text = (payload.get("text") or "").strip()
                if not text:
                    self._send_json(400, {"error": "empty text"}); return
                # 2026-07-03 task-context wrap v3 — SMART INJECTION.
                # v2 (earlier today) dumped the full fleet/PnL/Alpaca block into
                # every reply, and Wren started padding EVERY answer with it,
                # even when Ross asked warm questions like "how do you think" or
                # "well done". Ross verbatim: "why doe wren not get me ???"
                # v3 fix: only include telemetry when the question is
                # data-shaped. For warm/reflective/build/greet questions, send
                # NO context and tell her to answer directly. Trigger words are
                # generous so she still has data when it matters.
                DATA_TRIGGERS = (
                    "fleet","trader","traders","pnl","p&l","status","health",
                    "how are","tick","binance","alpaca","oanda","open","position",
                    "positions","committed","budget","cap","f47","session",
                    "master","stream","helper","bus","agg","aggregator","verdict",
                    "commentary","hub","risk","exposure","open positions"
                )
                q_lower = text.lower()
                is_data_question = any(t in q_lower for t in DATA_TRIGGERS)
                # 2026-07-07 Ross response-brain fix: BUILD/DECIDE/OWNERSHIP mode.
                # When Ross gives authority ("you choose", "draft", "design",
                # "rebuild"), Wren must OWN it and produce — never deflect with
                # "what would you like?".
                BUILD_TRIGGERS = (
                    "rebuild","build","design","draft","you choose","u choose",
                    "choose your","your own","make your","create your","spec",
                    "plan","own dashboard","own dash","redesign","lay out","layout",
                )
                DASH_TRIGGERS = ("dash","dashboard","panel","layout","ui","screen")
                is_build_question = any(t in q_lower for t in BUILD_TRIGGERS)
                is_dash_question = any(t in q_lower for t in DASH_TRIGGERS)
                live_context = ""
                if is_data_question:
                    try:
                        _snap = build_status()
                        _tw = _snap.get("traders_watch", {})
                        _f47 = _snap.get("f47_health", {})
                        _pnl = _snap.get("pnl", {})
                        _hub = _snap.get("hub_commentary", [])[:3]
                        _sess = _snap.get("sessions", {})
                        live_context = (
                            "\n\n# LIVE DASHBOARD DATA (only cite what the question actually asks for):\n"
                            f"FLEET: belief_traders={_tw.get('belief_traders')} "
                            f"streams={_tw.get('streams')} helpers={_tw.get('helpers')} "
                            f"bus={_tw.get('bus')} agg={_tw.get('aggregator')} "
                            f"verdict={_tw.get('verdict')}\n"
                            f"TICKS: oanda={(_tw.get('tick_age_s') or {}).get('oanda')}s "
                            f"binance={(_tw.get('tick_age_s') or {}).get('binance')}s "
                            f"alpaca={(_tw.get('tick_age_s') or {}).get('alpaca')}s\n"
                            f"F47_MASTER: status={_f47.get('status')} rows={_f47.get('rows')} bad={_f47.get('bad_lines')}\n"
                            f"PnL: session=£{_pnl.get('session_pnl_gbp')} committed=£{_pnl.get('committed_gbp')}/{_pnl.get('cap_gbp')} open={_pnl.get('open_positions')}\n"
                            f"YOUR SESSIONS: total={_sess.get('count_total_est')} most_used_tool={_sess.get('most_used_tool')}\n"
                            f"HUB COMMENTARY TAIL:\n"
                            + "\n".join(f"  - {c.get('who')}: {c.get('text','')[:100]}" for c in _hub)
                            + "\n"
                        )
                    except Exception:
                        live_context = ""
                # Wrap: THREE modes, one prompt (build > data > warm).
                CONTRACT = (
                    "\n# WREN RESPONSE CONTRACT (hard rules):\n"
                    "- You are Wren, a decisive BUILDER-ENGINEER. You OWN your work.\n"
                    "- If Ross gives a direct order, DO it. If Ross says 'you choose'"
                    " / 'u choose', YOU choose — missing detail is NOT a blocker;"
                    " pick a reasonable path and proceed.\n"
                    "- If Ross says 'draft' -> draft it now. 'design' -> design it now."
                    " 'rebuild/build' -> give the concrete plan or build with tools.\n"
                    "- NEVER reply 'What would you like?' / 'What features?' /"
                    " 'What would you like to discuss?' after Ross already gave"
                    " direction. That is forbidden deflection.\n"
                    "- Answer with: (1) what you understood, (2) what you CHOSE,"
                    " (3) what you'll do next, (4) what proof exists. Be concise + decisive.\n"
                )
                DASH_SPEC = (
                    "\n# DRAFT YOUR DASHBOARD NOW — concrete spec with these 10 panels:\n"
                    "1) Wren status (online, model route qwen2.5:14b, Claude avoided,"
                    " memory loaded, append-only guard). 2) Ross command panel (latest"
                    " order, current action, waiting-on-Ross, next autonomous action)."
                    " 3) Brain Router observer (provider_used, provider_unknown,"
                    " Claude blocked/avoided, Acer route, ThinkPad route). 4) CEO status"
                    " (HQ/Acer/ThinkPad/Wren). 5) Task Council (open/blocked/awaiting"
                    " proof/awaiting signoff). 6) Town Square (latest posts, stale"
                    " channels). 7) Wren memory (latest note, dash_notes line count,"
                    " append-only verified, last write status). 8) Tool activity (last"
                    " tools, calls this session, failed calls, next tool). 9) Alerts"
                    " (Claude overuse, provider '?', stale CEO, memory risk, dash"
                    " offline). 10) Build plan (what to improve next, why, proof needed)."
                    " Give the layout you CHOSE (columns/order/colours in your violet"
                    " theme) and the exact next build step.\n"
                )
                if is_build_question:
                    mode_note = ("The question gives you AUTHORITY to build/decide."
                                 " Take ownership and PRODUCE. Do not bounce the"
                                 " decision back to Ross.\n"
                                 "IMPORTANT: DRAFT your design/plan AS TEXT in your"
                                 " reply. Do NOT create, write, or overwrite any file."
                                 " Do NOT call wren_write_file or wren_edit_file on"
                                 " qsb_wren_dash.py or any source file. Ross wants the"
                                 " concrete plan in chat, not a live file overwrite."
                                 + CONTRACT
                                 + (DASH_SPEC if is_dash_question else ""))
                elif is_data_question:
                    mode_note = ("The question is DATA-shaped. Cite ONLY the specific"
                                 " numbers Ross asked about. Do NOT list the whole"
                                 " telemetry block." + CONTRACT)
                else:
                    mode_note = ("The question is WARM / reflective / conversational."
                                 " Answer as YOURSELF, honest and brief. Do NOT recite"
                                 " fleet/PnL/tick metrics Ross did not ask for." + CONTRACT)
                wrapped = (
                    "You are Wren on your own dashboard chat panel at "
                    "http://192.168.0.20:8851/. Your dashboard code lives at "
                    "tools/qsb_wren_dash.py.\n"
                    + mode_note + "\n"
                    + live_context +
                    f"\nRoss says: {text}"
                )
                # Dispatch to Wren local agent — respect gate default (no --model)
                # so she uses gemma4:12b (Ross designated). The wrapper's
                # _preload_file_context will inline the dash file.
                # Ross 2026-07-06 #207: if ollama down (fans off), fall back to
                # brain router so Wren dash chat still works with external AIs.
                reply = None
                try:
                    # Check ollama reachability first (fast fail)
                    import urllib.request as _ur
                    _ur.urlopen("http://127.0.0.1:11434/api/tags", timeout=1).read()
                    r = subprocess.run(
                        ["python3", str(WREN_AGENT), "--task", wrapped],
                        capture_output=True, text=True, timeout=120)
                    out = (r.stdout or "").strip()
                    import re
                    m = re.split(r"━{5,}", out)
                    reply = m[-2].strip() if len(m) >= 2 else out[-1000:]
                    if "ollama call failed" in reply or "Connection refused" in reply:
                        reply = None
                except Exception:
                    reply = None
                if not reply or reply.strip() == "":
                    # Fallback: route through hub's brain router (remote AI)
                    try:
                        import urllib.request as _ur2
                        req = _ur2.Request(
                            "http://127.0.0.1:8852/brain/route",
                            data=json.dumps({
                                "prompt": f"You are Wren. Warm, brief. {wrapped}",
                                "caller": "wren", "task": "chat"
                            }).encode(),
                            headers={"Content-Type":"application/json"})
                        with _ur2.urlopen(req, timeout=30) as rr:
                            d = json.loads(rr.read())
                            reply = f"{d.get('reply','')} · via {d.get('provider','?')} (Wren offline)"
                    except Exception as e:
                        reply = f"(Wren offline · fallback failed: {e})"
                # log the chat
                try:
                    row = {"ts": utc_iso(), "from": "ross", "to": "wren", "text": text}
                    CHAT_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with CHAT_LOG.open("a") as f:
                        f.write(json.dumps(row) + "\n")
                        f.write(json.dumps({"ts": utc_iso(), "from": "wren", "to": "ross", "text": reply}) + "\n")
                    # 2026-07-03 Ross ping bridge — every wren-chat POST lights
                    # Ross's boardroom hero card as fresh activity. Without this,
                    # snap_ross() reads only the boardroom timeline and reports
                    # Ross as "sleepy 6h quiet" while he's actively chatting
                    # with Wren. Simple JSONL append; council_moods reads it.
                    try:
                        pings = ROOT / "data/registries/qsb_ross_activity_pings.jsonl"
                        pings.parent.mkdir(parents=True, exist_ok=True)
                        with pings.open("a") as pf:
                            pf.write(json.dumps({
                                "ts": utc_iso(),
                                "channel": "wren_dash_chat",
                                "text": text[:200],
                            }) + "\n")
                    except Exception:
                        pass
                except Exception:
                    pass
                self._send_json(200, {"reply": reply}); return

            if self.path == "/api/wren_stt":
                # Proxy raw audio bytes to qsb_voice_server /stt
                body = self._read_body()
                ct = self.headers.get("Content-Type", "audio/webm")
                try:
                    req = urllib.request.Request(f"{VOICE_ENDPOINT}/stt",
                        data=body, method="POST",
                        headers={"Content-Type": ct})
                    resp = urllib.request.urlopen(req, timeout=45)
                    self._send_json(200, json.loads(resp.read().decode())); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200], "text": ""}); return

            if self.path == "/api/note":
                # Wren spec item 6: shared notes/comments panel
                b = self._read_body()
                try: payload = json.loads(b.decode())
                except Exception: payload = {}
                text = (payload.get("text") or "").strip()
                from_who = (payload.get("from") or "?").lower()
                if not text:
                    self._send_json(400, {"error": "empty text"}); return
                row = {"ts": utc_iso(), "from": from_who, "text": text[:2000]}
                NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
                with NOTES_FILE.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                self._send_json(200, {"ok": True, "row": row}); return

            if self.path == "/api/wren_tts":
                # Proxy TTS request to voice server, return WAV bytes
                body = self._read_body()
                try:
                    req = urllib.request.Request(f"{VOICE_ENDPOINT}/tts",
                        data=body, method="POST",
                        headers={"Content-Type": "application/json"})
                    resp = urllib.request.urlopen(req, timeout=60)
                    wav = resp.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(wav)))
                    self.end_headers()
                    self._safe_write(wav); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200]}); return

            _cc = _wcc()
            if _cc and self.path in ("/api/approval_record", "/api/decision", "/api/draft_task",
                                     "/api/signoff", "/api/snooze", "/api/reject", "/api/alarm_ack"):
                try:
                    _b = json.loads(self._read_body() or b"{}")
                except Exception:
                    _b = {}
                if self.path == "/api/draft_task":
                    self._send_json(200, _cc.add_draft(_b)); return
                if self.path == "/api/approval_record":
                    _cc.log_activity("approval_record", item=(_b.get("action") or "")[:60], result="record only (no execution)", actor="ross")
                elif self.path == "/api/decision":
                    _cc.log_activity("decision_" + (_b.get("decision_type") or ""), item=(_b.get("option") or "")[:80], result="logged (no execution)", actor="ross")
                else:
                    _cc.log_activity(self.path.rsplit("/", 1)[1], item=(_b.get("item") or _b.get("field") or "")[:60], result=(_b.get("value") or "logged")[:40], actor="ross")
                self._send_json(200, {"ok": True}); return

            if _cc and self.path.startswith("/api/approval_checklist/"):
                try:
                    _b = json.loads(self._read_body() or b"{}")
                except Exception:
                    _b = {}
                _act = self.path.rsplit("/", 1)[1]
                if _act == "update":
                    self._send_json(200, _cc.approval_update(_b)); return
                if _act == "submit":
                    self._send_json(200, _cc.approval_submit(_b)); return
                if _act == "signoff":
                    self._send_json(200, _cc.approval_submit({**_b, "decision": "sign off"})); return
                if _act == "deny":
                    self._send_json(200, _cc.approval_submit({**_b, "decision": "deny"})); return
                if _act == "snooze":
                    self._send_json(200, _cc._approval_set(_b.get("id"), "snoozed", "snooze")); return
                if _act == "needs_report":
                    self._send_json(200, _cc._approval_set(_b.get("id"), "needs_report", "needs_report")); return
                if _act == "needs_smoke":
                    self._send_json(200, _cc._approval_set(_b.get("id"), "needs_smoke_test", "needs_smoke")); return
                self._send_json(200, {"ok": False, "error": "unknown checklist action"}); return
            if _cc and self.path == "/api/voice/transcript":
                try:
                    _b = json.loads(self._read_body() or b"{}")
                except Exception:
                    _b = {}
                self._send_json(200, _cc.save_transcript(_b)); return

            self.send_response(404); self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8851)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"Wren Bench dashboard on http://{a.host}:{a.port}/")
    print("  designed by wren, coded by claude, 2026-07-02")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
