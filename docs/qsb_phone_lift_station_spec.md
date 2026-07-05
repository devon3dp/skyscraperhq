# Phone-Side Lift-Station — Design Spec (V1.5 draft)

**Status:** design, not yet implemented.
**Date:** 2026-06-14
**Why now:** The Galaxy receptionist (`tools/qsb_galaxy_receptionist.sh`) currently POSTs direct to `/api/f0/{greet,converse,close}` on the fortress dashboard. That violates CLAUDE.md's core rule: *"Inter-floor communication travels through lifts. Lifts carry sealed packets."* The phone is a satellite floor; it must speak lift, not raw HTTP.

## 1. Phone floor identity

- Propose **Floor 166 (`floor_166`)**, archetype `satellite_terminal`. F165 is already the cockpit's Vision Floor.
- Register in `data/registries/floors.json` (or its equivalent — to be verified against on-disk reality before adding; the master registry has drifted before, see `feedback`/`reference` memories).
- Lift zone: `ZONE A` via `main_low_rise` (which serves floors 0–15 and external satellites in current tower lift layout).

## 2. Sealed-packet shape (outbound: phone → tower)

```json
{
  "packet_id": "PKT-<10-char-uuid>",
  "ts": "2026-06-14T12:00:00Z",
  "source_floor": "floor_166",
  "target_floor": "floor_00",
  "lift_id": "main_low_rise",
  "intent": "receptionist.greet | receptionist.converse | receptionist.close",
  "priority": 5,
  "sealed_token": "<HMAC-SHA256 base64 of canonicalized fields>",
  "payload": { "caller_id": "...", "text": "...", "summary": "..." }
}
```

Canonicalized signature input:
`source_floor | target_floor | intent | sha256(payload_json) | ts`

## 3. Secret management

- Tower HMAC secret is **provisioned once** from the tower vault → phone vault.
- On phone: `/data/data/com.termux/files/home/.qsb_tower_secret` (mode 600).
- On tower: stored under `floors/floor_28_security_department/vault/.env.galaxy_lift` (new file).
- **Open question:** key rotation cadence + revoke path. Defer to security review.

## 4. Inbound shape (tower → phone)

**Simplest reliable path:** phone polls tower.
- Tower endpoint: `GET /api/lift_station/floor_166/messages?since=<ts>` (add to `src/dashboard/server.py`)
- Returns JSON array of pending sealed packets targeted at floor_166.
- Phone validates `sealed_token` before processing.
- Polling cadence: 500ms during active call, 2s idle.

Push (ADB-reverse callback) was considered and rejected — harder to make reliable on mobile.

## 5. Migration shape — receptionist script

Currently:
```bash
greeting="$(curl -s -m 5 -X POST "$FORTRESS/api/f0/greet" \
            -H 'Content-Type: application/json' \
            -d "{\"caller_id\":\"$caller\"}" | jq -r .text)"
```

Becomes:
```bash
greeting="$(lift_send 'receptionist.greet' \
            "$(jq -nc --arg c "$caller" '{caller_id:$c}')" | jq -r .payload.text)"
```

Where `lift_send <intent> <payload-json>` is a new shared function (sourced from `tools/qsb_phone_lift.sh`) that:
1. Builds the packet structure
2. Computes the HMAC sealed_token
3. POSTs to `/api/lift_station/send` on the fortress
4. Returns the sealed response

Three direct POSTs collapse to three `lift_send` calls.

## 6. Refusal modes — when the lift can't reach the tower

| Failure | Behaviour |
|---|---|
| Connection refused | Queue packet to `~/.qsb_outbox.jsonl`, retry every 5s |
| 5xx response | Same as above, max 5 retries, then mark `failed` + log |
| 4xx (sealed_token bad) | DO NOT retry — log, escalate via sentinel `health.pulse`, fail call gracefully ("the tower is not responding — let me take your number") |
| Token signature mismatch on inbound | DROP packet, log to `qsb_phone_outbox_audit.jsonl`, do not consume |

The phone never blocks the live caller on lift failure — degrades to a polite "we lost the link" script instead.

## 7. Tower-side additions needed

- `POST /api/lift_station/send` on the dashboard — receives sealed packet, validates token, routes to LiftNetwork, returns sealed reply
- `GET /api/lift_station/<floor>/messages` — pending-packets queue per floor
- Registry: `data/registries/lift_permissions.json` entry for `floor_166` (allowed intents = `receptionist.*`, sealed_packets_required = true)

## 8. What this spec does NOT decide yet

- Whether the lift-station also handles `health.pulse`, `announce.tannoy`, `audio.transcribe` intents (sentinel proposes them — receptionist scope is narrower, others land later as we add operatives)
- Key-rotation mechanism
- Sentinel ↔ lift-station ordering: sentinel filters at port 8866; lift-station listens at... a different port? same port? **Recommendation:** sentinel stays at 8866 (loopback edge), lift-station consumes from `sentinel_inbox.jsonl` rather than running its own port. Single edge, single bouncer.

## Sign-off needed before implementing

- Ross — yes on F166 number, yes on sentinel-fronts-lift-station architecture, yes on HMAC secret provisioning approach
- ~~Auger / Helm — adversarial review~~ — **DONE 2026-06-14 14:43 UTC, openai/gpt-4o-mini, $0.0002.**
- Bench gate review — the receptionist edit lives outside safety_paths_refused but is non-trivial; should land via the workshop bench with sigs, not direct write

## Auger verdict (2026-06-14): REDESIGN

Auger flagged four concrete issues that block ship as-drafted:

1. **Replay window is undersized.** Nonce-ring + ts is vulnerable to ring-wrap and survives a phone reboot if the ring is in-memory only. Auger suggests N≥100 packets minimum.
   **Fix:** Persist the last 1024 nonces to `~/skyscraperhqphone/lift_nonce_ring.jsonl`. On phone boot, load it. Add a per-floor `seq` counter that's strictly monotonic — reject any packet with `seq` ≤ last-seen-seq for that floor.

2. **Pipe-separated canonicalization is ambiguous.** If an `intent` ever contains `|`, the signature parses differently from what the signer intended (signature-malleability). Same risk if payload JSON re-serializes with different key order.
   **Fix:** Use a length-prefixed canonical form: `len(field) || field || ...`, each field in fixed order. Hash *that*, not a pipe-joined string. For the payload field, use a canonical-JSON library (sorted keys, no whitespace) before hashing.

3. **Token granularity too narrow.** `packet_id`, `priority`, `lift_id` are unsigned — an attacker who captures a packet can mutate priority or lift_id without breaking the signature.
   **Fix:** Sign every field that affects routing or precedence, not only payload-side fields. Add `packet_id`, `priority`, `lift_id` to the canonical input.

4. **Phone is a theft-risk; revocation is needed.** Exfiltrated phone HMAC secret = forge-anything-from-floor_166 until rotated.
   **Fix:** Tower keeps a `phones.json` registry of {floor_id, key_id, status}. Every sealed packet includes `key_id`. Tower rejects packets whose key_id is `revoked` or `expired`. Rotation: tower can mark a key_id revoked from the dashboard; phone re-provisions via a one-shot ADB push when next plugged in.

**Status:** spec rewrite required before any phone-side `lift_send` code is written. Open as task #6-redesign.
