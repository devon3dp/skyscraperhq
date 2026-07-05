# QSB Model Floor — Local API key configuration

This guide explains **only** how to provide API keys *locally* on your own
machine. Real keys must never:

- be pasted into Claude, ChatGPT, DeepSeek, or any chat surface
- be written into `data/registries/`
- be written into `data/logs/`
- be written into Godot scripts, scenes, or screenshots
- be committed to any git repository

## 1 — Copy the template

```
cd /vaults/nvme0/qsb_tower_v1
cp config/model_floors/.env.model_floors.template \
   config/model_floors/.env.model_floors.local
chmod 600 config/model_floors/.env.model_floors.local
```

`.env.model_floors.local` is gitignored by convention (verify before
committing). It lives on your local disk only.

## 2 — Edit it locally

```
nano config/model_floors/.env.model_floors.local
```

Fill the values for the providers you want to enable. Set the relevant
`*_ENABLED` flag to `1`. Set `QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=1`
only when you are ready for manually-initiated external calls.

## 3 — Load it for one shell session

```
set -a; source config/model_floors/.env.model_floors.local; set +a
```

The variables are now available to QSB bash scripts and any Godot launch
that inherits the shell environment.

## 4 — Or export inline

```
export QSB_OPENAI_API_KEY="..."
export QSB_OPENAI_MODEL="gpt-4o-mini"
export QSB_OPENAI_ENABLED=1

export QSB_DEEPSEEK_API_KEY="..."
export QSB_DEEPSEEK_MODEL="deepseek-chat"
export QSB_DEEPSEEK_ENABLED=1

export QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=1
```

Do **not** put real keys in this README, ever.

## 5 — Verify

```
./scripts/qsb_model_floor_status.sh
```

This prints **presence only** (`API key present: true/false`) and the
masked tail `...{last4}` when the key is present. It does not echo full
keys at any point.

## 6 — Disable on demand

```
./scripts/qsb_model_floor_disable_external_calls.sh
```

Sets `QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=0` and writes a clear off
record to `data/registries/qsb_model_floor_provider_status.json`.

## Cost guard defaults

| Variable | Default |
|---|---|
| `QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED` | `0` (off) |
| `QSB_MODEL_FLOOR_MAX_REQUESTS_PER_SESSION` | `5` |
| `QSB_MODEL_FLOOR_MAX_TOKENS_PER_REQUEST` | `1000` |
| `QSB_MODEL_FLOOR_LOG_PROMPTS` | `0` (off; never log prompt bodies) |
| `QSB_MODEL_FLOOR_MASK_SECRETS` | `1` (on) |

Even with `*_ENABLED=1`, every model floor still requires the global
`QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=1` to actually issue a request.
This is intentionally two locks.

## What the Claude floor needs

Nothing — the Claude floor is local advisory and runs without any API
key. It looks for the Claude CLI; if absent, it shows a "Claude CLI not
detected — floor stays in design-manifesto-only mode" message.
