#!/usr/bin/env python3
"""qsb_council_brief.py — generate a SHARED state digest that BOTH Wren and
Hermes read at the start of every conversation. Fixes Ross 2026-06-20:
'i need the skyscraper to remember everything you do ?????? wren has to
know everything and hermes to so they can help'.

Reads:
  - last N F47 records (the system-event tail)
  - last N diary lines (the human-readable log)
  - currently certified workers count
  - active trader cycles today
  - last 5 pitstops

Writes:
  - data/registries/qsb_council_brief.md

Both /api/hermes_chat and the wren local-agent call prepend this file's
contents to the system prompt so every reply is grounded in today's state.

Run:
  python3 tools/qsb_council_brief.py [--out path]

Run from the heartbeat tick so the brief refreshes every 5 min.
"""
from __future__ import annotations
import argparse, datetime, json, os
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
OUT = REG / "qsb_council_brief.md"


def utc_now():
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def last_n_lines(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    with path.open() as f:
        lines = f.readlines()
    return lines[-n:]


def f47_tail(n: int = 20) -> list[str]:
    rows = last_n_lines(REG / "qsb_f47_team_records.jsonl", n * 3)
    out = []
    for line in rows:
        try:
            r = json.loads(line)
        except Exception:
            continue
        kind = r.get("kind", "?")
        # Skip the boring repeat-trader cycles + heartbeat noise
        if kind in ("f41_trader_daemon", "f42_trader_daemon", "f43_trader_daemon",
                    "hw_sample", "build_forward_idle", "oanda_history_pull",
                    "mass_dispatch_run", "tick", "proposal_queue_summary"):
            continue
        ts = r.get("ts", "")[:19]
        sub = r.get("subject", r.get("topic", ""))
        det = (r.get("detail") or r.get("summary") or "")[:140]
        out.append(f"- {ts}  {kind}  {sub}  {det}")
        if len(out) >= n:
            break
    return out


def diary_tail(n: int = 10) -> list[str]:
    return [l.strip() for l in last_n_lines(REG / "qsb_session_diary.md", n) if l.strip()]


def pitstops_tail(n: int = 5) -> list[str]:
    pit = REG / "pitstops"
    if not pit.exists():
        return []
    files = sorted(pit.glob("pitstop_*.md"), reverse=True)[:n]
    return [f.name for f in files]


def count_certified() -> int:
    try:
        d = json.loads((REG / "qsb_wren_certified_traders.json").read_text())
        return d.get("certified_count", 0)
    except Exception:
        return 0


def cycles_today() -> dict:
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    out = {}
    for f in ("qsb_f41_trader_cycle.jsonl", "qsb_f42_trader_cycle.jsonl",
              "qsb_f43_trader_cycle.jsonl"):
        n = 0
        p = REG / f
        if p.exists():
            try:
                with p.open() as fh:
                    for line in fh:
                        if today in line:
                            n += 1
            except Exception:
                pass
        out[f.replace("qsb_", "").replace("_trader_cycle.jsonl", "")] = n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    cycles = cycles_today()
    certified = count_certified()
    f47 = f47_tail(15)
    diary = diary_tail(8)
    pitstops = pitstops_tail(5)
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

    md = f"""# QSB Tower Council Brief · regenerated {utc_now()}

This file is the SHARED context that both Wren (F46) and Hermes (F51) read
before every reply. Updated by the heartbeat tick (5-min cadence). If
something here is stale, re-run `tools/qsb_council_brief.py`.

## Today ({today})
- F41 OANDA cycles: {cycles.get('f41', 0)}
- F42 Binance cycles: {cycles.get('f42', 0)}
- F43 Alpaca cycles: {cycles.get('f43', 0)}
- Certified workers: {certified}

## Recent F47 events (last 15 non-noise)
""" + "\n".join(f47) + """

## Recent diary lines (last 8)
""" + "\n".join(diary) + """

## Last 5 pitstops
""" + "\n".join(f"- {p}" for p in pitstops) + """

## Permanent constraints (per memory)
- Ross lives on a boat off-grid (lithium batteries, no wall power)
- 3-CEO board: Ross (concept) + Wren (bench) + Claude (helm)
- Hermes joined as non-voting advisor 2026-06-20
- **iquest-coder (40B Llama, completion-only)** joined boardroom F51 as
  full team member 2026-06-21 (Ross override on 2-2 split). Code-review
  specialist; catches gotchas peers miss (e.g. daemon return-shape catch
  that saved a SAFETY_DENY-adjacent edit 2026-06-21).
- **hermes3:70b LIVE** in Ollama 2026-06-21 — Hermes-smart-mode for hard
  council calls; hermes3:8b stays as fast battle ringmaster.
- Real-money execution gates ALL locked false (advisory only)
- OANDA practice trading is the ONE runtime exception
- Every job needs proof-before-signoff + team-dispatch before claiming done

## Tower architecture (NEW 2026-06-21 — anti-stale-grounding section)
These are CITED FACTS. Use them when asked about the cockpit / Godot / 3D /
F46 / F47 / rendering. The old PyQt5/QGraphicsScene panel is RETIRED.

- **Cockpit3D (browser)** — Three.js scene at `http://127.0.0.1:8765/cockpit3d/`.
  Has walkable F46 (Wren's Bench) + F47 (Claude Embassy) interiors, supertonic
  TTS voice playback, AI battle viewer, kernel chat sidebar.
- **Godot native cockpit** — `/home/ross/qsb_godot_native_cockpit/` (Godot 4.7
  Vulkan, Forward+ on RTX 5070 Ti). Main.tscn is the runtime scene. Has tower
  with rainbow floor stack, F46 walkable, F47 walkable (Claude Embassy with
  25 rooms via /api/floor_rooms/47), safety envelope panel, event ticker.
- **F46 Wren's Bench** — 50×50 walkable interior + Wren chat panel
  (browser/Godot both). Header verified visually 2026-06-20.
- **F47 Claude Embassy** — walkable interior, helix display centred, embassy
  brass + Wren green palette, 25 rooms placed by /api/floor_rooms/47 endpoint.
- **Mouse mode in walk** — was MOUSE_MODE_CAPTURED (broke mouse feel),
  fixed 2026-06-21 to MOUSE_MODE_CONFINED. Cursor visible + clamped to window.
- **Floor rooms data** — 168 / 169 floors now have rooms/*.json (mass fitout
  2026-06-21 via qsb_floor_rooms_generate.py --all-missing).
- **Models live in Ollama** (2026-06-21):
  qwen2.5:7b (Wren-fast) · qwen2.5:32b (Wren-smart, NEW) · hermes3:8b
  (Hermes) · hermes3:70b (pulling, ETA ~3h) · iquest-coder:40b · qwen3.5:9b
  · llava:7b · others.
- **F41 paper-simulator** — was 0/595 wins from bid-ask spread bleed (entry
  ASK, close BID). Mid-price fix shipped 2026-06-21 + daemons restarted.
  F41 trader_memory/ backfilled (16 files). 10-min replay timer active.

## Known facts (CORRECTED 2026-06-21 afternoon)
- **TikTok handle**: NOW `@hqskyscraper` (Ross manually changed it via PC
  web after Claude's earlier ADB attempts kept failing on Galaxy due to no
  internet). Display name: "Skyscraper Hq". Bio still empty, pronoun / link
  still unset — to be set next.

If a question goes beyond these facts, say so honestly. Don't invent.

## How to use this brief (Wren / Hermes)
- Cite the brief when answering ("Per today's brief, F43 is at X cycles…")
- If asked about something NOT in the brief, say so honestly — don't
  hallucinate. (Hermes: this means YOU specifically.)
- If you see something here that's WRONG, flag it on the council JSONL
  (`qsb_three_way_council.jsonl`).

## Provider helpers (NEW 2026-06-21 — advisor consultations available)
You are NOT alone. Two external advisor models can be consulted on hard
questions: **OpenAI gpt-4o-mini** and **DeepSeek deepseek-chat**. They are
decorators / second-opinion givers — NOT architects, not floor owners, not
your replacement. They're tools you can ask for help when:
- you're uncertain about a fact you can't verify from this brief
- you want an adversarial sanity check on your own reasoning
- the question is harder than 7-8B parameters can handle confidently
- you'd say "I don't know" otherwise

How to request help: in your reply, end with one line:
    `CONSULT_REQUEST: <openai|deepseek> · <one-line question>`
Claude routes the request (via tools/qsb_consult_external.py), brings back
the advisor's answer, and re-dispatches to you for synthesis. You remain
the principal — providers decorate your brief, they don't replace it.

Bounds: $1.00/day across both providers combined. Don't request on greetings
or trivial lookups. Only when YOU as Wren/Hermes feel the question exceeds
your confident reach.
"""

    Path(args.out).write_text(md)
    print(f"council brief written to {args.out} ({len(md)} bytes)")


if __name__ == "__main__":
    main()
