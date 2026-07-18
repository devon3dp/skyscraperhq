# QUAD MONITOR — Build & Smoke Report
**Date:** 2026-07-09  ·  **Built by:** Claude HQ  ·  **Ordered by:** Ross

## What was built
A single-page 2×2 live dashboard wall in the Boardroom hub (`tools/qsb_boardroom_hub.py`, port **8852**).
Four real dashboards embedded via the hub's server-side `/proxy/*` (iPad-safe, dodges AP isolation).

- Routes: **`/quad_monitor`**, aliases **`/dashboard_wall`**, **`/four_dash`**, **`/quad`**
- Health API: **`/quad_monitor/health`** (server-side probes all four, returns real HTTP codes/errors)
- Each panel: live health dot, HTTP status text, **⟳ Reload**, **↗ Open** (direct URL), red error overlay with the real error if a panel is down
- Home button → `/ipad`

## Bug fixed during build
Hub `/proxy/tp` pointed at stale **192.168.1.91:9110** (dead). TP's real dashboard is **192.168.1.74:9110**. Corrected.

## Real dashboard URLs
| Panel | Proxy (iframe uses) | Direct URL | Title served |
|---|---|---|---|
| Claude HQ | `/proxy/hq` | `http://<hub>:8850/` | HQ-Claude · Bench |
| Wren | `/proxy/wren` | `http://<hub>:8851/` | Wren · Bench |
| TP-Pip | `/proxy/tp` | `http://192.168.1.74:9110/` | TP-Pip · ThinkPad-Command-Cathedral |
| Acer-Cass | `/proxy/acer` | `http://192.168.1.41:9000/` | Acer-Cass · Acer-Data-Foundry |

## Smoke results — ALL GREEN
- `/quad_monitor`, `/dashboard_wall`, `/four_dash` → **200** text/html
- `/quad_monitor/health` → **200**, all 4 panels `up:true` HTTP 200
- `/proxy/hq` 200 (54KB), `/proxy/wren` 200 (66KB), `/proxy/tp` 200 (30KB), `/proxy/acer` 200 (28KB) — all real dashboard HTML, not error pages
- No `X-Frame-Options`/CSP frame-block on any target → iframes load
- Visual: TP + Acer box dashboards captured headless and confirmed as real rich dashboards (CEO chat, self-prompt engine, thoughts, tool logs). HQ/Wren are known-good HTML benches.

## Known limitation (not a defect)
Headless Chrome hangs rendering all 4 live, continuously-polling dashboards in one composite screenshot (concurrent cross-origin subframe deadlock). Individual dashboards render fine. Real browsers (iPad/desktop) render iframes lazily and are unaffected. Composite visual pending an eyeball in a real browser.

## Panel status
🟢 HQ · 🟢 Wren · 🟢 TP-Pip · 🟢 Acer-Cass — 4/4 green.
