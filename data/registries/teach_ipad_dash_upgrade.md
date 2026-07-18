# TEACH · Upgrade /ipad dash — add /team_live features

**Author:** HQ-Claude (teacher, per R77)
**Audience:** TP, Acer, Wren — one claims, implements
**Ross order 2026-07-07 11:55 UTC:** add all new features + functions + animations to iPad dash

## What to add (from /team_live)

1. **Quorum strip** (top) — HQ/TP/Acer/Wren dots green/red, quorum count, speech toggle
2. **4-pane live view** — HQ · TP · Acer · Wren panes, each showing:
   - Connection endpoint + status
   - Recent 3 thoughts from that CEO's card
   - Commentary buttons (`say(ceo, text)`)
3. **Chat window** — posts to town-square, live scroll, latest 20 posts
4. **Speech synthesis** — SpeechSynthesis for commentary lines, toggle on/off
5. **Animations** — dot pulse on live status, chat msg slide-in, speech-active glow
6. **1.5s refresh tick** (was 500ms → slowed to 3s → now standardize to 1.5s to match team_live)
7. **Home button** (already present on iPad)

## Where the code lives

- Hub: `tools/qsb_boardroom_hub.py` (contains `IPAD_HTML` constant + `/ipad` route + `/team_live/data` endpoint)
- Related routes already built: `/team_live` (line ~7902), `/team_live/data`, `/team_live/say`

## How to add without breaking existing /ipad

**Option A (minimal):** Add a new `<section>` in `IPAD_HTML` called "team_live_inline" that iframes `/team_live` in a bordered card. Fast, no risk.

**Option B (rich):** Copy the JS + HTML blocks from `TEAM_LIVE_HTML` (quorum strip, 4-pane grid, chat, commentary buttons, speech) into `IPAD_HTML`. Better UX but riskier.

Recommend **A** for a first ship (R78-safe), **B** as follow-up after 2-CEO signoff.

## Test plan (before signoff)

```bash
# Original /ipad still works
curl -s -o /dev/null -w "HTTP %{http_code} · %{size_download}B\n" http://192.168.1.71:8852/ipad
# expect 200, size grew by ~200-1000 bytes (Option A) or ~5000 bytes (Option B)

# New section renders (visual only — grep for the new id)
curl -s http://192.168.1.71:8852/ipad | grep -c "sec-team-live-inline"
# expect ≥1

# Existing sections still all present
curl -s http://192.168.1.71:8852/ipad | grep -oE 'id="sec-[^"]+"' | wc -l
# expect ≥ 31 (baseline)
```

## R09 backup before edit

```bash
cp tools/qsb_boardroom_hub.py "tools/qsb_boardroom_hub.py.bak_$(date -u +%Y%m%dT%H%M%SZ)_ipad_upgrade"
```

## R78 signoff flow

1. Draft in sandbox (backup + edit + hub restart)
2. Run all 3 tests above — quote outputs
3. Post evidence to town-square + task note
4. 2 OTHER worker CEOs run the tests independently + peer_signoff approve
5. Then land (which is: hub already restarted; peer_signoff marks state=ready_to_ship)
6. done(task_id)

## HQ role per R77

I (HQ) do NOT implement this. I peer-review the diff + verify tests + can be one of the 2 signoffs. TP or Acer or Wren claims + writes the code.
