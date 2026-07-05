"""Comms — scaffold for skyscraper outbound + inbound channels.

Three channels modelled:

  · TELEGRAM   — bot account, scaffold ready. You create the bot with
                 @BotFather, paste the token into .env.comms; bridge
                 starts answering. Inbound messages route through the
                 same `kernel_dialogue_adapter` Lumen uses.
  · SMS        — Twilio (or Vonage) account. Operator's phone number
                 lives in an env var ONLY — never in code, never in a
                 registry. We refuse to send unless the env var is set.
  · EMAIL      — SMTP. Same env-var-only rule.

Hard rules:
  · Operator's phone, email, and bot token are NEVER persisted to disk
    in our registries. Snapshot reports only "configured: True/False".
  · No outbound message is sent unless `confirm_send=True` is passed AND
    the channel's gate is True.
  · Inbound messages route through kernel_dialogue_adapter — Lumen's
    same honest framing applies (topic match or honest "I don't know").

This scaffold writes only metadata + counts to the registry. The actual
Telegram long-poll loop is a separate Claude phase (gated by external
API access).
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import os
import time

from . import write_registry, append_log, now, SAFETY


# Env var names (NAMES are public; values stay in env)
ENV = {
    "telegram_bot_token":        "QSB_TELEGRAM_BOT_TOKEN",
    "telegram_admin_chat_id":    "QSB_TELEGRAM_ADMIN_CHAT_ID",
    "twilio_account_sid":        "QSB_TWILIO_ACCOUNT_SID",
    "twilio_auth_token":         "QSB_TWILIO_AUTH_TOKEN",
    "twilio_from_number":        "QSB_TWILIO_FROM_NUMBER",
    "operator_sms_to_number":    "QSB_OPERATOR_SMS_TO_NUMBER",   # masked in snapshot
    "smtp_host":                 "QSB_SMTP_HOST",
    "smtp_user":                 "QSB_SMTP_USER",
    "smtp_pass":                 "QSB_SMTP_PASS",
    "smtp_from":                 "QSB_SMTP_FROM",
    "operator_email_to":         "QSB_OPERATOR_EMAIL_TO",
}


def _mask_phone(p: Optional[str]) -> Optional[str]:
    if not p: return None
    p = str(p)
    if len(p) <= 4: return "***" + p[-2:]
    return "***" + p[-4:]


def _mask_email(e: Optional[str]) -> Optional[str]:
    if not e or "@" not in e: return None
    name, _, dom = e.partition("@")
    return (name[:1] + "***@" + dom) if name else "***@" + dom


def _present(name: str) -> bool:
    return bool(os.environ.get(name))


# ── per-channel status ───────────────────────────────────────────────

def telegram_status() -> Dict[str, Any]:
    return {
        "channel": "telegram",
        "configured": _present(ENV["telegram_bot_token"]),
        "admin_chat_id_set": _present(ENV["telegram_admin_chat_id"]),
        "outbound_enabled": False,        # gate stays False until external API allowed
        "inbound_enabled":  False,
        "engine": ("On Telegram poll/webhook events Lumen would route "
                    "the user's message through kernel_dialogue_adapter "
                    "and reply with the same honest framing."),
        "setup": [
            "1. In Telegram, search for @BotFather and start a chat.",
            "2. Send /newbot. Pick a name (e.g. 'QSB Skyscraper') + a username (e.g. qsb_skyscraper_bot).",
            "3. BotFather replies with a token shaped like: 1234:ABCD...",
            "4. Save it locally in /vaults/nvme0/qsb_tower_v1/.env.comms:",
            "     export QSB_TELEGRAM_BOT_TOKEN='1234:ABCD...'",
            "5. Send your bot any message; it'll record your chat_id once the bridge runs.",
            "6. The bridge phase enables the long-poll loop after your operator sign-off.",
        ],
        "bot_name_suggestion": "QSB Skyscraper (@qsb_skyscraper_bot)",
    }


def sms_status() -> Dict[str, Any]:
    return {
        "channel": "sms",
        "provider": "twilio_or_vonage",
        "configured": (_present(ENV["twilio_account_sid"])
                        and _present(ENV["twilio_auth_token"])
                        and _present(ENV["twilio_from_number"])),
        "operator_to_number_set": _present(ENV["operator_sms_to_number"]),
        "operator_to_number_masked": _mask_phone(
            os.environ.get(ENV["operator_sms_to_number"])),
        "outbound_enabled": False,        # gate stays False
        "setup": [
            "1. Open a Twilio trial account at twilio.com (free SMS credit).",
            "2. Buy or get assigned a phone number (UK numbers from £1/mo).",
            "3. In /vaults/nvme0/qsb_tower_v1/.env.comms add:",
            "     export QSB_TWILIO_ACCOUNT_SID='AC...'",
            "     export QSB_TWILIO_AUTH_TOKEN='...'",
            "     export QSB_TWILIO_FROM_NUMBER='+44...'",
            "     export QSB_OPERATOR_SMS_TO_NUMBER='+44XXXXXXXXXX'",
            "4. Run: scripts/qsb_comms_test_sms.sh    (sends 'Skyscraper ping' to your number)",
        ],
        "policy": ("Your phone number is read from env ONLY. It is NOT "
                    "stored in any cognitive registry, log, or git-tracked file."),
    }


def email_status() -> Dict[str, Any]:
    return {
        "channel": "email",
        "configured": (_present(ENV["smtp_host"])
                        and _present(ENV["smtp_user"])
                        and _present(ENV["smtp_pass"])
                        and _present(ENV["smtp_from"])),
        "operator_email_set": _present(ENV["operator_email_to"]),
        "operator_email_masked": _mask_email(
            os.environ.get(ENV["operator_email_to"])),
        "outbound_enabled": False,
        "setup": [
            "1. Choose an SMTP provider (Gmail with app password works; Mailgun is cleaner).",
            "2. Save credentials in /vaults/nvme0/qsb_tower_v1/.env.comms (NEVER in code).",
            "3. Use scripts/qsb_comms_test_email.sh to send yourself a test.",
        ],
    }


def snapshot() -> Dict[str, Any]:
    t = telegram_status(); s = sms_status(); e = email_status()
    return {
        "ok": True,
        "kind": "cognitive_comms_scaffold",
        "generated_ts": now(),
        "policy": (
            "Comms scaffold. NO outbound messages sent by the cognitive "
            "layer itself. NO credentials persisted to disk. Operator "
            "supplies env vars; a separate phase enables the bridges."
        ),
        "safety_envelope": dict(SAFETY),
        "channels": {
            "telegram": t,
            "sms": s,
            "email": e,
        },
        "env_var_names_in_use": dict(ENV),
        "any_channel_configured": (t["configured"] or s["configured"] or e["configured"]),
        "any_outbound_enabled":    False,    # always False from this layer
    }


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_comms_scaffold.json", snap)
    return snap


# ── Outbound helpers (refuse without confirm + creds) ───────────────

def send_telegram(text: str, chat_id: Optional[str] = None,
                    confirm_send: bool = False) -> Dict[str, Any]:
    """Refused until external_api_calls_enabled is True AND confirm_send is True
    AND token present. Records the refusal for audit."""
    if not confirm_send:
        return {"ok": False, "blocked": True,
                "reason": "confirm_send_required"}
    if not _present(ENV["telegram_bot_token"]):
        return {"ok": False, "blocked": True,
                "reason": "telegram_bot_token_missing"}
    return {"ok": False, "blocked": True,
            "reason": ("external_api_calls_enabled=False — a separate "
                        "Claude phase enables the long-poll bridge")}


def send_sms(text: str, to_number: Optional[str] = None,
               confirm_send: bool = False) -> Dict[str, Any]:
    if not confirm_send:
        return {"ok": False, "blocked": True, "reason": "confirm_send_required"}
    if not (_present(ENV["twilio_account_sid"])
            and _present(ENV["twilio_auth_token"])
            and _present(ENV["twilio_from_number"])):
        return {"ok": False, "blocked": True, "reason": "twilio_credentials_missing"}
    to = to_number or os.environ.get(ENV["operator_sms_to_number"])
    if not to:
        return {"ok": False, "blocked": True, "reason": "to_number_missing"}
    return {"ok": False, "blocked": True,
            "reason": "external_api_calls_enabled=False — separate phase"}


def send_email(subject: str, body: str,
                 to_addr: Optional[str] = None,
                 confirm_send: bool = False) -> Dict[str, Any]:
    if not confirm_send:
        return {"ok": False, "blocked": True, "reason": "confirm_send_required"}
    if not (_present(ENV["smtp_host"]) and _present(ENV["smtp_user"])):
        return {"ok": False, "blocked": True, "reason": "smtp_credentials_missing"}
    return {"ok": False, "blocked": True,
            "reason": "external_api_calls_enabled=False — separate phase"}
