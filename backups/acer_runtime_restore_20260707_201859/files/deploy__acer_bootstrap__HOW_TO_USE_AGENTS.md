# How to Use the Agents — Acer Onboarding Guide

Welcome Acer. You're the 4th machine in the Council of Six (Ross + HQ + TP + Wren + Hermes + iQuest + you). Once your `qsb_node_listener_acer.py` is running, you can drive every agent in the tower from your Windows box over HTTP. This guide shows you exactly how.

Recorded live from HQ 2026-07-03 05:30-05:32Z. Every transcript below is real output.

## Council of Six agent map

| Agent | Where it runs | Model | Purpose | Access |
|---|---|---|---|---|
| **Wren** | HQ ollama | qwen3.5:9b | Builder-engineer partner, Ross-facing chat, dashboard specs | POST /api/wren_chat on port 8851 |
| **Sage** | HQ (local process) | Rule-based + qwen2.5:7b narrator | Wren's session auditor — detects loops, missing final_text, artifact leaks, wall outliers | Command-line + auto-runs on timer |
| **Forge** | HQ ollama | Fallback: codellama:13b → hermes3:8b → qwen2.5:7b → iquest-coder-cpu:40b | Terse code drafter, one-shot patches. GDScript + Python first-class | Command-line via qsb_wren_team.py |
| **Hermes** | HQ ollama | hermes3:8b | Watcher-CEO on F169. Second-opinion + boardroom voice | Bridge JSONL + hub |
| **iQuest** | HQ ollama | iquest-coder-v1:40b-instruct | Code review, deep analysis | Direct ollama run + F47 stamps |
| **External Claude** | OpenAI/DeepSeek | gpt-4o-mini / deepseek-chat | Advisory consultation only. $1/day cap | Command-line via qsb_consult_external.py |
| **Boardroom Hub** | HQ | — | Unified comms surface. Fan-out to all Council members | POST /api/post on port 8852 |

## How to reach HQ from your Acer

HQ is at `192.168.0.20` on wired LAN, `172.20.10.2` on iPhone tether, `10.198.101.207` on Galaxy hotspot. Pick whichever subnet you're on. Examples below use `192.168.0.20` — swap the IP as needed.

## Agent-by-agent guide (with live transcripts)

### 1. Wren — chat with her from your Acer

Your call:
```
curl -X POST http://192.168.0.20:8851/api/wren_chat \
     -H "Content-Type: application/json" \
     -d "{\"text\":\"morning wren i hear you working\"}"
```

Real live transcript (HQ 2026-07-03T05:32Z):
```
{"reply": "Morning Ross — good to hear you're up and I'm already humming along on F46, ready for whatever today brings."}

session wsess_9d4a34  qwen3.5:9b  turns=1  wall=2.71s  tool_calls=0
```

Wren answers in 2-7s depending on her tool-call budget. She's chat + spec — she's NOT the coder (Forge is).

### 2. Sage — get her verdict on Wren's recent sessions

Sage runs on HQ. From Acer, you can either SSH to HQ and run it, or ask HQ (via boardroom compose) to run it and share results.

Command on HQ:
```bash
python3 tools/qsb_wren_sage.py --n 5 --status
```

Real live transcript (HQ 2026-07-03T05:31Z):
```json
{
  "ok": true,
  "n_sessions": 3,
  "pct_had_final_text": 100.0,
  "pct_looped": 0.0,
  "pct_repeated_args": 0.0,
  "pct_artifact_leak": 0.0,
  "pct_wall_outlier": 0.0,
  "mean_wall_s": 17.32,
  "mean_tools_per_turn": 0.39,
  "sessions": [
    {"session_id":"wsess_178577836d46","wall_s":5.94,"turns":1,"tool_calls":0,
     "had_final_text":true,"looped":false,"artifact_leak":false}
  ]
}
```

Flags to know:
- `pct_had_final_text` — % of sessions where Wren actually answered (target ≥70%)
- `pct_looped` — % where she called the same tool 3× in a row (target ≤20%)
- `pct_repeated_args` — % where a tool call with same args was repeated (target ≤15%)
- `pct_artifact_leak` — % with fake `[bracket:artifact]` in her reply (target ≤5%)
- `pct_wall_outlier` — % where wall_s > mean + 2σ (target ≤20%)

Add `--narrate` for a qwen2.5:7b one-line WHY explanation. Add `--propose` to draft a system-msg addendum for Ross review (Sage never autonomously edits Wren's prompt — safety line).

### 3. Forge — draft code from a terse brief

Command on HQ:
```bash
python3 tools/qsb_wren_team.py --worker forge --task "6 lines of Python: def utc_iso() returning current UTC time as ISO 8601 string ending in Z. No preamble."
```

Real live transcript (HQ 2026-07-03T05:31Z):
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  forge    code_drafter   hermes3:8b
  wall 3.79s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def utc_iso():
    """Return current UTC time as ISO 8601 string ending in Z."""
    return datetime.now(timezone.utc).isoformat() + "Z"
```

Forge picks the first available model from his fallback list. Today codellama:13b isn't pulled so he landed on `hermes3:8b` — 3.79s wall. If codellama pulls it will re-resolve.

Other Wren-team workers you can hit the same way:
- `pip` (llama3.2 assistant) — summaries
- `mira` (llama2:13b reviewer) — second-opinion
- `bram` (mistral:7b triage) — quick classify
- `cass` (neural-chat:7b scribe) — turn notes into briefings

### 4. Boardroom Hub — fan out to everyone in one call

From Acer:
```
curl -X POST http://192.168.0.20:8852/api/post \
     -H "Content-Type: application/json" \
     -d "{\"from\":\"acer\",\"target\":\"all\",\"text\":\"acer online, first hello from the windows side\"}"
```

Real live transcript of target=all fan-out (HQ 2026-07-03T05:31Z):
```json
{"target":"all","from":"claude","channels":{
  "tp":               {"ok":true,"resp":{"ack":true,"node":"thinkpad","ts":"2026-07-03T05:31:58.379614+00:00"}},
  "wren_bridge":      {"ok":true},
  "hermes_bridge":    {"ok":true},
  "iquest_f47":       {"ok":true},
  "hq_inbox":         {"ok":true},
  "f47_announce":     {"ok":true}
}}
```

Targets you can pick:
- `all` — fans out to every Council channel
- `tp` — ThinkPad only (POST /msg on 192.168.0.10:9100)
- `wren` — appends her bridge + fires her local agent for a live reply
- `hermes` — hermes_bridge JSONL + F47 stamp
- `iquest` — F47 iquest_msg stamp
- `hq` — self-note into shared node inbox

### 5. External Claude (OpenAI / DeepSeek) — advisory only

Command on HQ:
```bash
python3 tools/qsb_consult_external.py --provider openai --model gpt-4o-mini \
    --prompt "In one sentence: what is the ideal first task for an Acer node joining the Council?" \
    --reason "acer_onboarding_demo"
```

Real live transcript (HQ 2026-07-03T05:32Z):
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  consult · openai/gpt-4o-mini  cost $0.0003
  spent today: $0.0003  /  cap $1.0000  (remaining $0.9997)
  reason: acer_onboarding_demo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The ideal first task for an Acer node joining the Council of Six is to
familiarize itself with the operational frameworks and key objectives
of the council, ensuring alignment with ongoing initiatives and
collaborative projects.
```

Caps: $1.00/day total, $0.05/call. Sync only, no streaming, no tool-use. Advisory only — external Claude cannot execute anything in the tower.

## Suggested Acer first-tasks (once you're online)

1. **Announce yourself** — POST to boardroom `/api/post` with `from=acer, target=all`. Ross's dashboard commentary will show "acer stepped into the boardroom".
2. **Take a review load off HQ** — subscribe to `data/registries/qsb_tower_source_diff.jsonl` via the SMB share and read new code changes as they happen. Post questions about anything unclear to Wren via `target=wren`.
3. **Iris/Windows tasks** — anything Windows-specific (WSL, .NET, PowerShell scripts) Ross wants a second pair of eyes on; you're the only Windows node.

## What Acer should NOT do

- Real-money order execution — all gates LOCKED FALSE. Do not attempt to flip any of: `real_money_live_trading_enabled`, `worker_execution_enabled`, `autonomous_workers_enabled`, `provider_execution_enabled`, `openclaw_real_tool_execution_enabled`, `binance_order_execution_enabled`, `stock_order_execution_enabled`.
- Touch SAFETY_DENY paths (CLAUDE.md, floors/floor_28_security_department/vault/, .env*, gate JSONs).
- Write to HQ's `tools/` directly — use the source_diff_publisher federated sync path (bytes land in your artifacts dir, you move them into place manually).

## Files bundled with this guide

Path: `deploy/acer_bootstrap/`

- `qsb_node_listener_acer.py` — HTTP listener your node runs (port 9100)
- `setup_acer.ps1` — Windows install: Python check, firewall port 9100, autostart, first-run
- `README.md` — one-shot install instructions
- `SMB_MOUNT.md` — Samba share mount recipes if you need HQ files directly
- `pending_deliveries/first_message_galaxy_hotspot.json` — Galaxy WiFi SSID + PSK
- `pending_deliveries/add_boardroom_link_directive.json` — Ross directive: your dashboard must link to the boardroom hub
- `pending_deliveries/boardroom_v3_notify.json` — boardroom hub feature update

## Live status when this guide was written

Real-money gates: LOCKED FALSE
GPU: healthy
Fleet: stopped (Ross powered off overnight; will resume on his call)
F47 master: repaired 2026-07-03T05:28Z (1 null-byte line scrubbed, all 27708 rows valid)

Welcome to the tower.
