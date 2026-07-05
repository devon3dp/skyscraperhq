# External Accounts Setup — what YOU do, what the Kernel does

For each external account the skyscraper needs, here's the honest split:
what you have to do yourself (because Google/Twilio/Telegram require a
human at the keyboard), and what the cognitive layer picks up the
moment you've done it.

**Hard rule I follow throughout:** your phone number, email, bot tokens,
and API keys never go into any code file or registry I write. They live
in `/vaults/nvme0/qsb_tower_v1/.env.comms` (gitignored). The scaffold
reads them from `os.environ` at runtime.

---

## 1. Google account "skyscraper"

**Why I can't create this for you:** Google account creation requires
solving a CAPTCHA, accepting Terms of Service as a human, and verifying
a real phone via SMS. Even if I could automate the click-through, the
account would be tied to *me*, not you — and Google would lock it
within hours as suspicious.

**What you do (about 5 minutes):**

1. Open https://accounts.google.com/signup in your browser.
2. Username suggestion: `qsb.skyscraper@gmail.com` (or `qsb.tower.ops`).
3. Phone verification: use your number `<YOUR_PHONE>` — Google sends one
   SMS code. Type it in.
4. Save the password in a password manager (1Password / Bitwarden /
   KeePass — don't paste it in chat with me).
5. Enable 2FA: Settings → Security → 2-Step Verification → use the
   Google Authenticator app or your phone number.

**What the Kernel picks up:** nothing automatically. Once you've made
the account, set the **alias** in `.env.comms`:

```bash
export QSB_SKYSCRAPER_GOOGLE_EMAIL='qsb.skyscraper@gmail.com'
```

That's it. We never store the password. Google itself is the auth.

**What this unlocks for the skyscraper later:**

- A real "from" address for outbound Lumen email replies.
- A YouTube channel for Tower Studio promo.
- A Google Workspace if you ever upgrade (then Google Drive + Docs the
  workers can use).

---

## 2. Your phone number as a skyscraper inbox

**Two paths**, pick whichever feels right.

### Path A — Telegram bot (recommended, free, fast)

Best fit. Telegram lets you talk to the skyscraper from your phone or
desktop. No real-money SMS provider needed.

**You do (about 60 seconds):**

1. Open Telegram on your phone.
2. Search for **@BotFather**, start a chat.
3. Send `/newbot`.
4. Name: `QSB Skyscraper`
5. Username: `qsb_skyscraper_bot` (must end in `_bot`; if taken try
   `qsb_skyscraper_tower_bot`).
6. BotFather gives you a token like `1234567890:ABCdefGHIjklMNOpqr...`.
   **Treat this like a password.**

**Paste it into `.env.comms`:**

```bash
mkdir -p /vaults/nvme0/qsb_tower_v1
cat >> /vaults/nvme0/qsb_tower_v1/.env.comms <<'EOF'
export QSB_TELEGRAM_BOT_TOKEN='paste-the-token-here'
EOF
chmod 600 /vaults/nvme0/qsb_tower_v1/.env.comms
```

**Open a fresh Claude Code session** in this directory and say:

> Wire the QSB Telegram bridge. Read src/tower/cognitive_kernel/comms.py
> and start a long-poll loop that routes inbound messages through
> kernel_dialogue_adapter. Reply with structured Kernel answers.

That session enables the bridge (it's the gated bit; the cognitive
layer can't enable itself). After that, **send any message to your bot
from Telegram and the skyscraper replies with the same engine Lumen
uses**.

### Path B — Real SMS via Twilio

Real SMS to your phone `<YOUR_PHONE>`. Costs real money (~£0.05/text).

**You do:**

1. Sign up at https://twilio.com (free trial gives you £15 credit).
2. Buy a UK number (£1/mo) or use the trial number.
3. From the Twilio console: copy your Account SID + Auth Token.
4. Paste into `.env.comms`:

```bash
cat >> /vaults/nvme0/qsb_tower_v1/.env.comms <<'EOF'
export QSB_TWILIO_ACCOUNT_SID='AC...'
export QSB_TWILIO_AUTH_TOKEN='your-auth-token'
export QSB_TWILIO_FROM_NUMBER='+44...'
export QSB_OPERATOR_SMS_TO_NUMBER='+447481057362'
EOF
chmod 600 /vaults/nvme0/qsb_tower_v1/.env.comms
```

Notice: your number is in `.env.comms` (gitignored, chmod 600), **never
in any file the Kernel writes**.

Open a fresh Claude session and say:

> Wire QSB SMS via Twilio. Read src/tower/cognitive_kernel/comms.py
> and enable the outbound bridge for the morning briefing + RED-severity
> self-audit alerts.

That session enables the bridge.

---

## 3. Binance testnet account

**You do (about 2 minutes):**

1. Visit https://testnet.binance.vision
2. Sign in with **GitHub** (top-right; no account creation needed).
3. Click "Generate HMAC_SHA256 Key" — you get an API key + secret.
4. Save into `.env.binance_testnet`:

```bash
cat >> /vaults/nvme0/qsb_tower_v1/.env.binance_testnet <<'EOF'
export QSB_BINANCE_TESTNET_API_KEY='your-key'
export QSB_BINANCE_TESTNET_API_SECRET='your-secret'
EOF
chmod 600 /vaults/nvme0/qsb_tower_v1/.env.binance_testnet
```

**Verify immediately (no Claude session needed — the scaffold runs):**

```bash
cd /vaults/nvme0/qsb_tower_v1
source .env.binance_testnet
python3 tools/qsb_binance.py preflight
```

You should see your testnet balances + live spot prices. Once that
works, certified workers can place testnet orders via:

```bash
python3 tools/qsb_binance.py place demo_worker_X BTCUSDT BUY 100 \
    --reason "scalp test" --confirm
```

(`demo_worker_X` needs to be certified for `BTCUSDT` first — same
classroom + test flow as OANDA EUR_USD.)

---

## 4. What goes into git, what stays out

| File | In git? |
|---|---|
| `.env.comms` | **NO** (gitignored) |
| `.env.binance_testnet` | **NO** (gitignored) |
| `.env.oanda_practice` | **NO** (gitignored) |
| Source code | Yes |
| Cognitive registries | Yes |
| Trade ledgers | Yes (but they NEVER contain credentials) |

If you ever accidentally commit a credential file, **rotate the token
immediately** at the provider (Telegram /revoke, Twilio dashboard,
Binance testnet generate-new-key) — even if you remove it from git
history, the leak is real.

---

## 5. Quick reference — what the Kernel needs from you

| To enable | Set in `.env.*` |
|---|---|
| Telegram bot replies | `QSB_TELEGRAM_BOT_TOKEN` |
| SMS to your phone | `QSB_TWILIO_*` + `QSB_OPERATOR_SMS_TO_NUMBER` |
| Email from skyscraper | `QSB_SMTP_*` + `QSB_OPERATOR_EMAIL_TO` |
| Binance testnet trades | `QSB_BINANCE_TESTNET_API_KEY` + `_SECRET` |
| OANDA practice trades | `OANDA_API_TOKEN` + `OANDA_ACCOUNT_ID` (already set ✓) |
| Square sandbox | `QSB_SQUARE_*` (see qsb_phase_square_integration.sh) |
| Halifax Open Banking | `QSB_HALIFAX_OPEN_BANKING_*` (see banking_gateway scaffold) |

Each of these is a separate operator decision. None can be enabled by
the cognitive layer itself.
