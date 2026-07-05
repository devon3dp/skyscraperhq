# QSB Galaxy Sentinel — first-gateway bouncer for the phone node

**Where it runs:** Termux on Ross's Galaxy SM_A156E (R5CX7098VJR), part of QSB Tower V1.5.

**What it does:** Accepts JSON packets on `127.0.0.1:8866 POST /ingest`, drops anything that's not from an allow-listed IP / not a known intent / not the right shape / rate-limited / replayed, and fans the survivors out to a JSONL inbox file. Workers read the inbox.

**What it does NOT do:**
- Execute payloads
- Call out to the tower
- Unwrap sealed lift packets
- Decide tower business

It's a *bouncer*, not an operative.

## Run

```bash
python tools/qsb_galaxy_sentinel.py
# logs to stderr; audit + inbox land on SD card
```

## Smoke test

```bash
curl -s localhost:8866/health | python -m json.tool

curl -s -X POST localhost:8866/ingest \
  -H 'Content-Type: application/json' \
  -d '{"intent":"health.pulse","ts":"2026-06-14T12:00:00Z","nonce":"'$(uuidgen)'","payload":{"battery":74}}'
```

Expected: 202 `{"ok":true,"queued":true}`. Repeat with same nonce → 409 `replay_nonce`.

## Env-var contract

| Var | Default | Meaning |
|---|---|---|
| `QSB_SENTINEL_ALLOW` | `127.0.0.1` | CSV of source IPs allowed to POST /ingest |
| `QSB_SENTINEL_INTENTS` | `health.pulse,call.ingest,announce.tannoy` | CSV of accepted intents |
| `QSB_SENTINEL_RPM` | `60` | Token-bucket refill rate per source IP |
| `QSB_SENTINEL_AUDIT` | `~/skyscraperhqphone/qsb_sentinel_audit.jsonl` | Audit log (every allow + drop) |
| `QSB_SENTINEL_INBOX` | `~/skyscraperhqphone/sentinel_inbox.jsonl` | Fan-out file workers tail |

## Worker integration

Workers tail `sentinel_inbox.jsonl` and act on packets that match their intent. The sentinel does NOT manage worker read offsets — workers track their own via a sibling file (`sentinel_inbox.<worker>.offset`) so restarts resume cleanly.

Workers may NOT POST to /ingest themselves. The sentinel is the network edge; workers consume from the file.

## Lift discipline

Replies that need to reach the tower go through the phone lift-station (see `docs/qsb_phone_lift_station_spec.md`), not back through the sentinel. The sentinel never originates outbound traffic.

## Mount discipline

Mount the SD card as `~/skyscraperhqphone` BEFORE launching the sentinel — otherwise the daemon creates the dir under Termux home and you lose logs on phone reset. The sentinel checks dir existence at boot.

## Shutdown

`kill -TERM <pid>` — audit is flushed, server closes cleanly.

## Audit log format

```json
{"ts":"...","node":"galaxy_phone","version":"1.5.0","event":"allow|drop","source":"127.0.0.1","intent":"health.pulse","reason":null,"audit_id":"<hex>"}
```

Drop reasons (enumerated by the code, not free text):
`unknown_path`, `source_not_allowed`, `rate_limited`, `bad_content_length`,
`missing_content_length`, `body_too_large`, `body_too_large_actual`, `bad_json`,
`bad_shape:*`, `intent_not_allowed`, `replay_nonce`, `fanout_io_error`,
`shutdown_signal`.

## Status

- 2026-06-14 — drafted by F47 fleet + general-purpose agent, code at `tools/qsb_galaxy_sentinel.py`
- Not yet deployed to phone
- Not yet smoke-tested locally
- Bench gate (`maintenance_auto_repair_enabled`) is enabled; this file lands via Wren operator direct-write because it's a brand-new tool, not a mutation of safety-tagged code
