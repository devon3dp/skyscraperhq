# Open Day — Morning Briefing

## 1. Status at a glance
{N} of 7 surfaces green; cloudflared dark; sentinels armed; heartbeat PID {HEARTBEAT_PID}; F47 bench gate enabled; F41 kill-switch armed.

## 2. Where to be at 09:00
Open `http://localhost:8765/welcome` in a fresh browser tab — that is what a first-time visitor sees. In a second terminal, tail the security audit:

```
tail -F data/registries/qsb_dashboard_security_audit.jsonl
```

Any path-traversal probe or unauthorized hit shows up there in real time. Keep that terminal in view until the first hour is over.

## 3. Surfaces ready
| Surface | URL / handle | Note |
|---|---|---|
| F0 Reception (Iris) | `/api/f0/greet` | Greeting endpoint live |
| /welcome | `/welcome` | Brass theme, 12-floor directory |
| /cockpit | `/cockpit` | Operator view, Open Day tagged |
| Lumen | `:8848` | Humanized greeting |
| Tower Studio | `:8849` | Back online via systemd-user |
| Vision Floor | `:8821` | Rebranded "The Vision Room" |
| F47 Embassy rooms | `floors/floor_47_executive_operations_department/rooms/` | 5/25 shipped (Batch 1 done) |
| Telegram bot | handle TBD | Waiting on BotFather token in vault/.env.telegram |

## 4. Surfaces NOT ready yet (cover language)
- **Voice line / phone reception** — "The real voice line is in commissioning — we'd love to take your call via Telegram in the meantime."
- **Payments / shops checkout** — "The shop is in soft-open; orders are taken by hand today. Leave your details with Iris."
- **Real-money trading desks (Binance, stocks)** — "The trading floor is running practice books today; live desks open after the regulatory review."
- **Autonomous workers acting on external systems** — "Workers are advisory today; every action goes through the operator."

## 5. The hard rules for the day
- F41 trading: PRACTICE ONLY. Confirm OANDA kill-switch armed and instrument whitelist loaded BEFORE doors open.
- cloudflared must be hard-down before doors open. Loopback only. Verify with `pgrep cloudflared` returning empty.
- No promises about payments, real-money trading, voice phone, or any abandoned-path capability. If unsure, say "in commissioning."

## 6. If something goes wrong
- Consult Helm (Ross-facing) or Auger (Wren-facing) via `tools/qsb_consult_external.py` for an advisory second opinion before any gate flip.
- Kill-switches: F41 at `data/registries/qsb_floor41_killswitch.json`; bench auto-apply at `data/registries/qsb_proposal_autoapply_gate.json`; heartbeat via `kill {HEARTBEAT_PID}`.
- Audit trail: `data/registries/qsb_tower_activity_tail.jsonl` (all events), `qsb_code_apply_audit.jsonl` (patches), `qsb_dashboard_security_audit.jsonl` (probes), `qsb_f47_agent_lessons.jsonl` (what the team has been learning).

— Wren, F47 / written 2026-06-14 the night before
