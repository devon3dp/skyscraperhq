# Phone↔Tower Lift-Station Spec V2

**Status:** design only — no code yet. Implementation gated on §10 sign-off.
**Date:** 2026-06-14
**Supersedes:** `docs/qsb_phone_lift_station_spec.md` (v1, verdict REDESIGN by Auger)
**Authority:** CLAUDE.md core rule — *"Inter-floor communication travels through lifts. Lifts carry sealed packets."* The Galaxy phone is a satellite floor and must speak lift, not raw HTTP into `/api/f0/*`.

---

## §1 Phone floor identity

Verified `data/registries/floors.json` (165 entries; max id = `floor_164`). v1's claim that *"F165 is the cockpit's Vision Floor"* is wrong — Vision Department is `floor_13`. F165 is free.

| field | value |
|---|---|
| id | `floor_165` |
| number | 165 |
| zone | `satellite` (new zone) |
| archetype | `satellite_terminal` |
| department | Galaxy Receptionist |
| lift_access | `low_rise` only |
| status | active |

Tower side: append entry to `floors.json`; add `"satellite"` to allowed_zones on `main_low_rise` in `lift_permissions.json`.

*Why this beats v1:* uses the actual next free floor (165, not 166) and stops citing a non-existent F165 collision.

---

## §2 Sealed packet shape v2 (Auger finding #2, #3)

Every field below is signed *except* `sig` itself.

| field | type | signed | notes |
|---|---|---|---|
| `v` | int = 2 | yes | spec version |
| `packet_id` | string `PKT-<26-char ulid>` | yes | replay-detect aux |
| `ts` | RFC 3339 UTC | yes | tower rejects skew > 120 s |
| `seq` | uint64 | yes | strictly monotonic per `(source_floor, key_id)` |
| `source_floor` | `floor_165` | yes | |
| `target_floor` | `floor_00` etc. | yes | |
| `lift_id` | `main_low_rise` | yes | now signed |
| `priority` | 0–9 | yes | now signed |
| `intent` | dotted, e.g. `receptionist.greet` | yes | |
| `key_id` | string `k_<8-hex>` | yes | enables revocation |
| `payload` | JSON object | yes | hashed via RFC 8785 |
| `sig` | base64(HMAC-SHA256) | — | the signature itself |

**Canonicalization:** **RFC 8785 (JSON Canonicalization Scheme)** over the packet object with `sig` removed. Chosen over length-prefix because (a) the packet is already JSON, so one serializer covers payload + envelope, (b) RFC 8785 has reference libs in Python/Rust/Go/JS; length-prefix is bespoke and easier to get wrong. JCS gives a unique byte sequence regardless of key order or whitespace; HMAC over that sequence is the `sig`.

*Why this beats v1:* eliminates pipe-delimiter ambiguity, locks routing fields into the signature, makes payload re-serialization safe.

---

## §3 Signing-key lifecycle (Auger finding #4)

**Generation.** Tower-side, `tools/qsb_phone_key_mint.py` (to be built). 32 random bytes via `secrets.token_bytes(32)`, base64-encoded. Mint requires Ross + Wren sigs.

**`key_id` format:** `k_<8-hex>` derived from `sha256(key_bytes)[:8]`. Stable, non-secret, safe to log.

**Provisioning.**
- Tower: `floors/floor_28_security_department/vault/.env.galaxy_lift` — lines `KEY_<key_id>=<base64>` (mode 600). Vault is a CLAUDE.md safety-tagged path; bench can't edit it.
- Phone: `/data/data/com.termux/files/home/skyscraperhqphone/.qsb_lift_key` — single line `<key_id>:<base64>` (mode 600). One-shot ADB push during physical pairing.
- Registry: new `data/registries/phones.json` — one row per `key_id` with `{floor_id, key_id, status, minted_ts, last_seen_ts, last_seq, rotated_from}` where `status ∈ {active, revoked, expired, pending}`.

**Rotation cadence.** 30 days default; tower flags `status=expired` 7 days before. Operator triggers re-pair via ADB.

**Revocation flow.** Dashboard button → `phones.json` row flipped to `revoked` → tower `/api/lift_station/send` rejects any packet whose `key_id` is not `active`. Revocation is instant; no grace period.

*Why this beats v1:* v1 had a single tower-wide HMAC secret with no rotation path. v2 keys are per-phone, individually revocable, and have a documented lifecycle.

---

## §4 Replay defence (Auger finding #1)

Tower-side state under `data/registries/lift_station/`:

| file | role |
|---|---|
| `seq_state.json` | `{key_id: last_seq_accepted}` — primary defence |
| `nonce_ring.jsonl` | last **1024** `packet_id`s per `key_id`, append-only, LRU eviction by count; loaded into memory at boot |

**Tower check order on inbound packet:**
1. `key_id` exists in `phones.json` and `status=active` → else 401
2. `sig` validates against canonicalized bytes → else 401
3. `|now − ts| ≤ 120 s` → else 408
4. `seq > seq_state[key_id]` → else 409 (replay)
5. `packet_id` not in nonce_ring[key_id] → else 409 (replay)
6. Accept: update `seq_state[key_id] = seq`, append `packet_id` to ring (evict oldest if > 1024).

`seq_state.json` and `nonce_ring.jsonl` are flushed on every accept (fsync). Phone keeps `~/skyscraperhqphone/lift_seq.json` (last-sent seq) so reboots don't reset.

*Why this beats v1:* `seq` is the primary defence (single integer, can't be exhausted), nonce ring is belt-and-braces, both survive reboot, ring size explicit at 1024 with LRU policy.

---

## §5 Packet flows

**Outbound (phone → tower).**
phone composes packet → JCS-canonicalize → HMAC-SHA256 with active key → POST to `https://<fortress>/api/lift_station/send` → tower validates (§4) → routes packet to target floor via LiftNetwork → tower returns a *sealed reply packet* (same shape, `source_floor=target`, `target_floor=floor_165`, signed with tower's reply key).

**Inbound (tower → phone).** Poll-only (push rejected as v1).
- `GET /api/lift_station/floor_165/messages?since_seq=<n>` every 500 ms during active call, 2 s idle.
- Tower returns array of sealed reply packets enqueued for floor_165 with `seq > since_seq`.
- Phone validates each (`sig`, tower `key_id` from local pinned tower pubkey table), processes, advances `since_seq`.

*Why this beats v1:* explicit reply-packet shape (v1 was vague about whether replies were sealed); since-seq polling instead of since-ts (no clock-skew bugs).

---

## §6 Refusal modes

| condition | behaviour |
|---|---|
| Connection refused / 5xx | queue to `~/skyscraperhqphone/lift_outbox.jsonl`, retry 5 s × 5; then mark `failed`, sentinel `health.pulse` |
| 408 ts-skew | re-stamp `ts` + bump `seq`, retry once; else fail |
| 409 replay | local bug — log to `lift_outbox_audit.jsonl`, do **not** retry, sentinel alert |
| 401 sig / key_id revoked | hard stop; degrade caller script to *"we've lost the link — let me take your number"*; sentinel alert with severity=high |
| Inbound `sig` mismatch | drop packet, log, do not consume |

Phone never blocks a live caller on lift failure.

*Why this beats v1:* distinguishes 401 (revoked key, hard) from 409 (replay, bug) from 408 (skew, recoverable) — v1 lumped all 4xx together.

---

## §7 Tower-side endpoints to add

In `src/dashboard/server.py`:

| method | path | role |
|---|---|---|
| POST | `/api/lift_station/send` | accept outbound sealed packet from any satellite, run §4 checks, route, return sealed reply |
| GET | `/api/lift_station/<floor>/messages?since_seq=<n>` | drain pending packets for `<floor>` |
| POST | `/api/lift_station/phones/<key_id>/revoke` | operator-only, flips `phones.json` row to `revoked` |
| GET | `/api/lift_station/phones` | dashboard read-only listing |

Loader for `phones.json` and `seq_state.json` lives in new module `src/tower/lift_station/`. Revoke endpoint requires Ross-dashboard auth (existing pattern).

*Why this beats v1:* v1 named only the first two endpoints; revocation had no surface.

---

## §8 Phone-side daemon

| item | value |
|---|---|
| binary | `~/skyscraperhqphone/bin/qsb_lift_stationd` (Bash + `jq` + `openssl dgst -sha256 -hmac`; or Python if shipped) |
| invoked by | Termux `sv` service, started at boot via `~/.termux/boot/start_lift_stationd` |
| upstream | reads `sentinel_inbox.jsonl` (sentinel still fronts port 8866; lift-station consumes from inbox, runs no own port — same as v1) |
| downstream | calls fortress `/api/lift_station/send` |
| polling thread | hits `/api/lift_station/floor_165/messages` on cadence in §5 |
| state files | `lift_seq.json`, `lift_outbox.jsonl`, `lift_outbox_audit.jsonl`, `.qsb_lift_key` |
| receptionist hook | exposes shell function `lift_send <intent> <payload-json>` sourced from `tools/qsb_phone_lift.sh` |

Sentinel keeps its bouncer role (already validates loopback origin); lift-station daemon is sentinel-trusted and reads from the inbox queue. Single edge, single port.

*Why this beats v1:* names the actual binary, boot path, and state files — v1 was hand-wave.

---

## §9 Migration: receptionist script

Current call in `tools/qsb_galaxy_receptionist.sh`:

```bash
greeting="$(curl -s -m 5 -X POST "$FORTRESS/api/f0/greet" \
            -H 'Content-Type: application/json' \
            -d "{\"caller_id\":\"$caller\"}" | jq -r .text)"
```

V2 replacement — `lift_send` builds a v2 packet with every signed field:

```bash
greeting="$(lift_send \
  --intent   receptionist.greet \
  --target   floor_00 \
  --lift     main_low_rise \
  --priority 5 \
  --payload  "$(jq -nc --arg c "$caller" '{caller_id:$c}')" \
  | jq -r '.payload.text')"
```

`lift_send` internally:
1. Reads `key_id` + key bytes from `.qsb_lift_key`.
2. Reads + atomically increments `lift_seq.json` for `key_id`.
3. Builds packet `{v:2, packet_id, ts, seq, source_floor:floor_165, target_floor, lift_id, priority, intent, key_id, payload}`.
4. JCS-canonicalizes, HMAC-SHA256, attaches `sig`.
5. POSTs to `/api/lift_station/send`.
6. On 200, validates reply `sig` against tower key, returns reply packet on stdout.
7. On non-200, applies §6 refusal logic.

Three direct POSTs in the receptionist (`greet`, `converse`, `close`) collapse to three `lift_send` calls.

---

## §10 Open questions for Ross sign-off

1. **F165 number confirmed?** (v1 proposed F166 against a non-existent collision; v2 proposes F165.)
2. **Per-phone keys (recommended)** vs. single tower-wide key with `key_id=k_default`? Per-phone is the design above.
3. **30-day rotation cadence** — too slow / too fast? Boat power realities may make 90 days more humane.
4. **Revocation UI** — dashboard button OK, or do you want a CLI-only path (`tools/qsb_phone_revoke.py`) to avoid accidental clicks?
5. **`phones.json` registry** — does it live under `data/registries/` (normal) or under `floors/floor_28_security_department/vault/` (vault-protected, bench can't edit)? Recommend vault.
6. **JCS library choice** — Python `rfc8785` package (PyPI) is the obvious pick on tower side; phone side uses `jq -S -c` as a *practical* JCS approximation. Acceptable, or ship Python on phone?
7. **Bench gate** — the receptionist edit, the new tower endpoints, and the `floors.json` append should all land via the F47 workshop bench under the 2026-06-13 multi-sig rule, *not* direct write. Confirm.
8. **Sentinel ↔ lift-station ordering** carried over from v1 §8 — sentinel-fronts-lift-station via inbox queue. Confirm still wanted.

Once §10 returns sign-off, the spec is implementable end-to-end without further design loops.
