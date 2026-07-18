# Receptionist Dashboard V1

A Pi-touchscreen **receptionist control desk** for the QSB Tower. Pure web
dashboard — **no Pico / GPIO / serial dependency**.

## What it is
- `tools/qsb_receptionist_dash.py` — self-contained HTTP server on **:8856**.
- Big, touch-friendly buttons; responsive on phone / tablet / PC; works in
  Chromium full-screen; no keyboard needed for basic use.

## Open it from the Pi
```
http://192.168.1.72:8856
```
(If HQ's LAN IP changes, find it on HQ with: `hostname -I` — use the `192.168.x.x`.)

## Truth rules (no fake green)
- Every "online" light is a **real live HTTP probe**. If an endpoint does not
  answer → **OFFLINE** (never a fake online).
- **Tour Guide** shows **NOT BUILT YET** until a real endpoint answers.
- **TP-Pip** = `192.168.1.74:8871` / DESKTOP-9RBVKSM / Lenovo ThinkPad.
- **Acer-Cass / Asa** = `192.168.1.41:8872` / DESKTOP-1E2FB5N / Acer Aspire A315-56.
- **Wren** = OBSERVER / GUARDIAN. **Claude HQ** = COORDINATOR / ARCHITECT.
- Status labels: LIVE · STALE · OFFLINE · COSMETIC · NOT BUILT YET · NEEDS APPROVAL.

## Routes
| Route | Method | Purpose |
|---|---|---|
| `/` `/visitor` | GET | desk page · public visitor page |
| `/health` | GET | liveness JSON |
| `/api/state` `/api/public_state` | GET | live probe of every node · visitor-safe view |
| `/api/links` | GET | action-button links + ready flags |
| `/api/brief` `/api/approvals` `/api/issues` `/api/handover` `/api/inbox` | GET | V1C desk panels |
| `/api/latest_reports` | GET | most recent `*REPORT*.txt` from the runs folder |
| `/api/floors` | GET | full floor directory (real cards) + live status |
| `/api/floor/<n>` | GET | one floor |
| `/api/floor_search?q=` | GET | "take me to floor" — search by number/name/dept/lead |
| `/api/comms` `/api/comms/{gmail,whatsapp,telegram}` | GET | truthful comms channel status (no bodies) |
| `/api/checkin` | POST | append a visitor check-in |
| `/api/note` | POST | append a note (`kind:ross_attention`/`freeze_request`/`intake_draft`) |

## V1F — Working Desk (checklists, buttons, activity feed, drafts)
- **Today** tab: desk status, top issue, next approval, latest report/note/check-in, counts.
- **Checklist** tab: a real board (`qsb_receptionist_checklist.json`, seeded once). Each item has
  buttons — ✓ Done · Clear · Snooze · Needs appr. · Keep watching · Add note · Draft task.
  **Clear never deletes** — it marks `cleared` and keeps the row in history; the active view hides it.
- **Activity** tab: `qsb_receptionist_activity.jsonl` — every action (status_checked, item_done/clear/
  snooze, needs_approval, note_added, draft_task_created…) is logged so Ross can watch her working.
- **Drafts** tab: draft-task tray → `qsb_receptionist_work_queue.json`. Saved `draft_only`,
  `needs_approval:true`. **Never submitted** to Task Council.
- **Approvals** tab: rich cards (why / risk / touches / not-allowed / suggested / status).
- Extra routes: `/api/desk_today` `/api/checklist(/add|update|done|clear|snooze)` `/api/approval_queue`
  `/api/activity` `/api/draft_task` `/api/draft_tasks` `/api/receptionist_drive`.
- She observes, logs, drafts, checks off, clears, guides — **she never executes work**.

## V1D — Floor Directory + Communications Desk
- **Floors tab**: 170 real floors from `floors/floor_*/floor_card.json`. Search box
  ("47", "Claude", "Wren", "Boardroom", "Reception") routes Ross to the floor; floors
  with a live dashboard get an Open button, the rest show their path. Status is honest:
  LIVE / OFFLINE / PARTIAL / NOT BUILT YET / UNKNOWN (never faked). Directory snapshot:
  `data/registries/qsb_receptionist_floor_directory.json`.
- **Comms tab**: Telegram / WhatsApp / Gmail / Voice(Twilio) status. LIVE only if a real
  process is running or a log is fresh (<24h); else PARTIAL / NEEDS WIRING. **No sending,
  no reading message bodies, no tokens/phone numbers** — only row-counts + timestamps.

## Writes (append-only, safe)
- `data/registries/qsb_receptionist_events.jsonl` — check-ins + notes + Ross flags.
- `data/registries/qsb_receptionist_status.json` — last computed state snapshot.

## What it does NOT do
- No task execution, no autonomous commands, no TP/Acer runtime commands,
  no provider/API-key access, no trading, no file deletion, no Pico/GPIO/serial.

## Run
```
# manual foreground
python3 tools/qsb_receptionist_dash.py

# background
nohup scripts/start_receptionist_dash.sh >/tmp/qsb_receptionist.log 2>&1 &
```

## Optional boot-persistence (needs separate approval to enable)
A unit file is provided at `scripts/qsb-receptionist-dash.service`. To make it
survive reboot (requires sudo, separate approval):
```
sudo cp scripts/qsb-receptionist-dash.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now qsb-receptionist-dash.service
```
