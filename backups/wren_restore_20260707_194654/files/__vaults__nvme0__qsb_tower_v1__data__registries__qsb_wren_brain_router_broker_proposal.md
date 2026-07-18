# Brain Router Broker — HQ initial proposal

## Architecture
- Single HTTP daemon `tools/qsb_brain_router_broker.py` on port :8792 (localhost)
- Endpoint: `POST /route`  with body `{provider?, task, prompt, actor, budget_hint?}`
- Broker reads vault key by provider; if provider omitted, picks per policy (fast=Groq/Kimi, deep=Anthropic/OpenAI, cheap=DeepSeek)
- Wraps existing `qsb_consult_external.py` (single-shot) + `qsb_provider_agent.py` (agentic) as backends — no duplicate provider code
- Returns `{ok, provider_used, model, response, cost_usd, tokens_in, tokens_out, ts, journal_id}`

## Communication protocol
- HTTP JSON in-process → simplest, transparent
- Callers (HQ/TP/Acer/Wren tools) do `curl POST /route` OR `qsb_brain_router.py` imports it

## Routing strategy
1. Explicit provider if named
2. Task-type hint: `code` → DeepSeek/Kimi, `chat` → Anthropic, `fast_summary` → Groq, `image` → refuse (not authorized)
3. Fallback chain if primary fails (Anthropic → OpenAI → DeepSeek)
4. Enforce existing budget caps (`$1/day` advisory + `$10/day` agentic)

## Error handling
- Per-provider timeout 20s
- Circuit breaker: 3 fails in 60s → skip that provider for 5 min
- Return `{ok: false, tried: [providers], last_error}` — never fabricate a response

## Logging
- Journal: `data/registries/qsb_brain_router_broker_journal.jsonl` — every call
- Metrics: rolling 24h calls-per-provider + spend + latency P50/P95

## Dash
- New route `/broker` on hub (:8852) — table of recent calls, provider spend gauges, per-actor breakdown, kill-switch button

## Integration points
- HQ/TP/Acer/Wren existing helper `qsb_brain_router.py` gets a thin `route_external()` function that POSTs to :8792 — no change to callers
- Auto-launches with hub via existing systemd or bash startup

## Modular add-provider
- Drop `.env.<newprovider>` in vault + add stanza to `PROVIDER_ADAPTERS` dict in broker
- No other code touched
