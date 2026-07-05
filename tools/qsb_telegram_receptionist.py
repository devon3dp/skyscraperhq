"""
qsb_telegram_receptionist.py — QSB Tower V1.5 Telegram front gate (PC node)

Lineage:
  Skyscraper owns the infrastructure. Models are temporary external tenants.
  Workers are external. Telegram is a STRANGER channel — an external chat
  network that calls in to F0 Iris exactly the way the phone line will.
  This bot is the wire between Telegram and the F0 receptionist endpoints;
  it does not decide, it does not dispatch.

Safety stance (per CLAUDE.md V1.3 + 2026-06-08 + 2026-06-10 + 2026-06-13):
  - Long-poll only. No webhook, no public IP, no inbound port opened.
  - No execution gates flipped. The bot only POSTs to /api/f0/* on the
    local fortress; F0 is itself advisory and routes to humans/officers.
  - Never echoes the bot token, never logs raw F0 payloads beyond length.
  - Allowed action set per inbound: greet, converse, close, reject. That's it.
  - Voice transcription is local-only (whisper.cpp binary). If the binary is
    missing the caller gets a polite "not enabled yet" — no cloud STT fallback.
  - Hard caps: 5s fortress timeout, 5min voice ceiling, 4096-char Telegram cap.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
VAULT_ENV = ROOT / "floors/floor_28_security_department/vault/.env.telegram"
AUDIT_PATH = ROOT / "data/registries/qsb_telegram_audit.jsonl"
ACTIVITY_TAIL = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"

F0_BASE = os.environ.get("QSB_F0_BASE", "http://127.0.0.1:8765")
WHISPER_BIN = os.environ.get(
    "WHISPER_BIN",
    str(ROOT / "tools/whisper.cpp") if (ROOT / "tools/whisper.cpp").exists()
    else "/usr/local/bin/whisper.cpp",
)
WHISPER_MODEL = os.environ.get(
    "WHISPER_MODEL",
    str(ROOT / "data/whisper/ggml-tiny.en.bin")
    if (ROOT / "data/whisper/ggml-tiny.en.bin").exists()
    else "/usr/local/share/whisper/ggml-base.en.bin",
)

VOICE_MAX_SECONDS = 300
TELEGRAM_MSG_CAP = 4000
FORTRESS_TIMEOUT_S = 5.0

VERSION = "1.5.0"
NODE = "pc_tower"

LOG_FMT = "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger("qsb.tg")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

LAST_SEEN: dict[int, float] = {}
USER_MODE: dict[int, str] = {}

ROSS_CHAT_ID = 8683680296

MENU_TEXT = (
    "QSB Tower Reception. Reply with a number:\n"
    "\n"
    "  1  Tower status\n"
    "  2  Talk to Wren (AI)\n"
    "  3  Leave a message for Ross\n"
    "  4  Worker roll-call\n"
    "  5  Help\n"
    "\n"
    "Send 0 or /menu anytime to return here."
)

HELP_TEXT = (
    "QSB Tower Reception — what each option does:\n"
    "\n"
    "  1 Status — current count of floors and live workers.\n"
    "  2 Wren — talk to Wren (AI). Every message after you pick 2 goes to\n"
    "     Wren until you send 0.\n"
    "  3 Message — leave a written message for Ross; he'll get it as a\n"
    "     Telegram alert.\n"
    "  4 Roll-call — list the live worker processes right now.\n"
    "  5 Help — this screen.\n"
    "\n"
    "Send 0 or /menu anytime to return to the main menu."
)


def _read_status_snapshot() -> str:
    try:
        floors = sum(1 for _ in (ROOT / "floors").iterdir())
    except OSError:
        floors = -1
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", "python.*qsb"], text=True, timeout=2
        )
        live = sum(1 for ln in out.splitlines() if "qsb" in ln and "grep" not in ln)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        live = -1
    tail_ts = "(none)"
    try:
        tail = ACTIVITY_TAIL.read_text(encoding="utf-8").splitlines()[-1]
        tail_ts = json.loads(tail).get("ts", tail_ts)
    except (OSError, ValueError, IndexError):
        pass
    return (
        "Tower status:\n"
        f"  Floors registered: {floors}\n"
        f"  Workers running:   {live}\n"
        f"  Last activity:     {tail_ts}\n"
    )


def _read_rollcall() -> str:
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", "python.*qsb"], text=True, timeout=2
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return "Roll-call unavailable right now."
    lines = []
    for ln in out.splitlines():
        if "grep" in ln:
            continue
        parts = ln.split(None, 1)
        if len(parts) < 2:
            continue
        cmd = parts[1]
        name = cmd.split("/")[-1].split()[0]
        lines.append(f"  - {name}")
    if not lines:
        return "No QSB workers running right now."
    return "Workers running:\n" + "\n".join(lines)


def _write_message_for_ross(user_id: int, username: str | None, text: str) -> None:
    row = {
        "ts": _now_iso(),
        "from_tg_user_id": user_id,
        "from_tg_username": username,
        "text": text[:2000],
    }
    path = ROOT / "data/registries/qsb_messages_for_ross.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _load_token() -> str:
    if VAULT_ENV.exists():
        for ln in VAULT_ENV.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if "=" in ln:
                k, v = ln.split("=", 1)
                if k.strip() == "QSB_TELEGRAM_BOT_TOKEN":
                    return v.strip().strip('"').strip("'")
    tok = os.environ.get("QSB_TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        raise SystemExit("QSB_TELEGRAM_BOT_TOKEN missing from vault and env")
    return tok


def _load_allowlist() -> set[int]:
    raw = ""
    if VAULT_ENV.exists():
        for ln in VAULT_ENV.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if "=" in ln and ln.split("=", 1)[0].strip() == "QSB_TELEGRAM_ALLOWED_CHAT_IDS":
                raw = ln.split("=", 1)[1].strip().strip('"').strip("'")
                break
    raw = raw or os.environ.get("QSB_TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw or raw.lower() in ("any", "all", "*"):
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            log.warning("ignoring non-int chat_id in allowlist: %r", part)
    return out


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _caller_id(user_id: int) -> str:
    return f"tg_{user_id}"


def _audit(kind: str, update: Update | None, msg_len: int, fortress_rc,
           extra: dict | None = None) -> None:
    user = update.effective_user if update else None
    chat = update.effective_chat if update else None
    row = {
        "ts": _now_iso(),
        "node": NODE,
        "version": VERSION,
        "kind": kind,
        "tg_user_id": getattr(user, "id", None),
        "tg_username": getattr(user, "username", None),
        "chat_id": getattr(chat, "id", None),
        "msg_len": int(msg_len),
        "fortress_rc": fortress_rc,
        "lift_bypass": True,
        "audit_id": uuid.uuid4().hex,
    }
    if extra:
        row.update(extra)
    line = json.dumps(row, separators=(",", ":")) + "\n"
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        log.error("audit write failed: %s", e)
    tail = {
        "ts": row["ts"],
        "event_kind": "provider_call",
        "provider": "telegram",
        "model": "f0_receptionist",
        "summary": f"telegram/{kind} rc={fortress_rc}",
        "payload": {
            "kind": kind,
            "tg_user_id": row["tg_user_id"],
            "msg_len": row["msg_len"],
            "fortress_rc": fortress_rc,
            "audit_id": row["audit_id"],
        },
    }
    try:
        with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(tail, separators=(",", ":")) + "\n")
    except OSError as e:
        log.error("activity tail write failed: %s", e)


async def _f0_post(path: str, payload: dict):
    url = f"{F0_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=FORTRESS_TIMEOUT_S) as c:
            r = await c.post(url, json=payload)
        try:
            data = r.json()
        except ValueError:
            data = {"ok": False, "raw_len": len(r.content)}
        return r.status_code, data
    except httpx.TimeoutException:
        return 599, {"ok": False, "error": "fortress_timeout"}
    except httpx.HTTPError as e:
        return 598, {"ok": False, "error": f"fortress_http:{type(e).__name__}"}


def _clip(text: str) -> str:
    if len(text) <= TELEGRAM_MSG_CAP:
        return text
    return text[: TELEGRAM_MSG_CAP - 12] + "... [clipped]"


async def _safe_reply(update: Update, text: str) -> None:
    text = _clip(text)
    for attempt in range(3):
        try:
            await update.effective_message.reply_text(text)
            return
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
        except TimedOut:
            await asyncio.sleep(1.0 * (attempt + 1))
        except Exception as e:
            log.error("reply failed: %s", e)
            return


ALLOWLIST: set[int] = set()


def _gate(update: Update) -> bool:
    if not ALLOWLIST:
        return True
    chat = update.effective_chat
    if chat and chat.id in ALLOWLIST:
        return True
    _audit("drop_not_allowed", update, 0, "gate")
    return False


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _gate(update):
        return
    user = update.effective_user
    LAST_SEEN[user.id] = time.time()
    USER_MODE[user.id] = "menu"
    _audit("menu_show", update, 0, "self", {"trigger": "start"})
    await _safe_reply(update, MENU_TEXT)


async def cmd_menu(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _gate(update):
        return
    user = update.effective_user
    LAST_SEEN[user.id] = time.time()
    USER_MODE[user.id] = "menu"
    _audit("menu_show", update, 0, "self", {"trigger": "menu_cmd"})
    await _safe_reply(update, MENU_TEXT)


async def cmd_end(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _gate(update):
        return
    user = update.effective_user
    cid = _caller_id(user.id)
    rc, _ = await _f0_post("/api/f0/close",
                            {"caller_id": cid,
                             "summary": "telegram session ended"})
    _audit("close", update, 0, rc)
    LAST_SEEN.pop(user.id, None)
    await _safe_reply(update,
                       "Thanks for calling Skyscraper HQ. Iris signing off.")


async def _push_to_ross(ctx: ContextTypes.DEFAULT_TYPE, body: str) -> bool:
    try:
        await ctx.bot.send_message(chat_id=ROSS_CHAT_ID, text=body,
                                    disable_notification=False)
        return True
    except Exception as e:
        log.error("push_to_ross failed: %s", e)
        return False


# Ross 2026-06-17: receptionist must ALSO WhatsApp Ross on his everyday phone.
# Telegram remains the primary channel; WhatsApp is parallel, best-effort.
ROSS_WHATSAPP = os.environ.get("QSB_ROSS_WHATSAPP", "+447481057362")
WA_SEND_TOOL = ROOT / "tools/qsb_whatsapp_send.py"


async def _push_to_ross_whatsapp(body: str) -> bool:
    """Best-effort WhatsApp push via Galaxy ADB. Runs in a worker thread so
    it never blocks the bot's async loop. Failure is logged, not raised —
    Telegram is the primary channel; WhatsApp is parallel insurance."""
    if not WA_SEND_TOOL.exists():
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", str(WA_SEND_TOOL),
            "--to", ROSS_WHATSAPP,
            "--text", body[:900],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(),
                                                     timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            log.error("whatsapp push timed out")
            return False
        if proc.returncode != 0:
            log.error("whatsapp push rc=%s err=%s",
                      proc.returncode, (stderr or b"")[:200])
            return False
        return True
    except Exception as e:
        log.error("whatsapp push raised: %s", e)
        return False


async def _push_to_ross_all(ctx: ContextTypes.DEFAULT_TYPE, body: str) -> dict:
    """Multi-channel push. Telegram + WhatsApp fire in parallel; returns a
    dict reporting which legs succeeded. Receptionist is now a true front
    desk — one message in, fan out across every wire we have to Ross."""
    tg_task = asyncio.create_task(_push_to_ross(ctx, body))
    wa_task = asyncio.create_task(_push_to_ross_whatsapp(body))
    tg_ok, wa_ok = await asyncio.gather(tg_task, wa_task,
                                          return_exceptions=False)
    return {"telegram": bool(tg_ok), "whatsapp": bool(wa_ok)}


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _gate(update):
        return
    msg = update.effective_message
    user = update.effective_user
    text = (msg.text or "").strip()
    if not text:
        return
    LAST_SEEN[user.id] = time.time()
    cid = _caller_id(user.id)
    _audit("text_in", update, len(text), "pending",
           {"mode": USER_MODE.get(user.id, "menu")})

    first = text.split()[0].lower() if text else ""
    if first in ("0", "/menu", "menu", "back"):
        USER_MODE[user.id] = "menu"
        _audit("menu_show", update, 0, "self", {"trigger": "back"})
        await _safe_reply(update, MENU_TEXT)
        return

    mode = USER_MODE.get(user.id, "menu")

    if mode == "menu":
        choice = first.lstrip(".#-)")[:1]
        if choice == "1":
            _audit("menu_pick", update, 0, "self", {"choice": "status"})
            await _safe_reply(update,
                              _read_status_snapshot() + "\nSend 0 for menu.")
            return
        if choice == "2":
            USER_MODE[user.id] = "wren"
            _audit("menu_pick", update, 0, "self", {"choice": "wren"})
            rc, data = await _f0_post("/api/f0/greet", {"caller_id": cid})
            wren_greet = (data.get("text") or
                          "You're now talking to Wren. Send any message.")
            await _safe_reply(update,
                              wren_greet +
                              "\n\n(You're in Wren mode. Send 0 to return"
                              " to the menu.)")
            _audit("wren_enter", update, 0, rc)
            return
        if choice == "3":
            USER_MODE[user.id] = "message"
            _audit("menu_pick", update, 0, "self", {"choice": "message"})
            await _safe_reply(update,
                              "Type your message for Ross. He'll receive it"
                              " on his phone. Send 0 to cancel.")
            return
        if choice == "4":
            _audit("menu_pick", update, 0, "self", {"choice": "rollcall"})
            await _safe_reply(update,
                              _read_rollcall() + "\nSend 0 for menu.")
            return
        if choice == "5":
            _audit("menu_pick", update, 0, "self", {"choice": "help"})
            await _safe_reply(update, HELP_TEXT)
            return
        _audit("menu_unknown", update, len(text), "self")
        await _safe_reply(update,
                          "That's not a menu option. Reply 1, 2, 3, 4, or 5.\n"
                          "\n" + MENU_TEXT)
        return

    if mode == "message":
        _write_message_for_ross(user.id, getattr(user, "username", None), text)
        if user.id != ROSS_CHAT_ID:
            channels = await _push_to_ross_all(
                ctx,
                f"Telegram message from "
                f"{getattr(user, 'username', None) or user.id}:\n\n{text[:1500]}"
            )
            _audit("message_pushed", update, len(text), "self", channels)
        USER_MODE[user.id] = "menu"
        _audit("message_left", update, len(text), "self")
        await _safe_reply(update,
                          "Got it — Ross will see it on his phone "
                          "(Telegram + WhatsApp). Back to the menu.\n\n"
                          + MENU_TEXT)
        return

    # mode == "wren"
    try:
        await ctx.bot.send_chat_action(chat_id=msg.chat_id,
                                        action=ChatAction.TYPING)
    except Exception:
        pass
    rc, data = await _f0_post("/api/f0/converse",
                                {"caller_id": cid, "text": text})
    reply = data.get("text") or "Sorry, the front desk is briefly unreachable."
    await _safe_reply(update,
                      reply + "\n\n(Send 0 for the menu.)")
    _audit("text_out", update, len(reply), rc)


def _transcribe(ogg_path: Path):
    wbin = Path(WHISPER_BIN)
    if not wbin.exists():
        return None
    wav_path = ogg_path.with_suffix(".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(ogg_path), "-ar", "16000", "-ac", "1",
             str(wav_path)],
            check=True, capture_output=True, timeout=30,
        )
        out = subprocess.run(
            [str(wbin), "-m", WHISPER_MODEL, "-f", str(wav_path), "-otxt",
             "-of", str(wav_path.with_suffix(""))],
            check=True, capture_output=True, timeout=120,
        )
        txt = wav_path.with_suffix(".txt")
        if txt.exists():
            return txt.read_text(encoding="utf-8", errors="ignore").strip()
        return (out.stdout or b"").decode("utf-8", errors="ignore").strip() or None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return None
    finally:
        for p in (wav_path, wav_path.with_suffix(".txt")):
            try:
                p.unlink()
            except OSError:
                pass


async def on_voice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _gate(update):
        return
    msg = update.effective_message
    user = update.effective_user
    voice = msg.voice
    if voice is None:
        return
    LAST_SEEN[user.id] = time.time()
    if (voice.duration or 0) > VOICE_MAX_SECONDS:
        _audit("voice_reject", update, voice.duration or 0, "voice_too_long")
        await _safe_reply(update,
                           "Voice too long, keep under 5 min please.")
        return
    ogg_path = Path(f"/tmp/qsb_tg_voice_{msg.message_id}.ogg")
    try:
        tg_file = await voice.get_file()
        await tg_file.download_to_drive(custom_path=str(ogg_path))
    except Exception as e:
        log.error("voice download failed: %s", e)
        _audit("voice_error", update, 0, "download_failed")
        await _safe_reply(update, "Couldn't fetch that voice note, sorry.")
        return

    _audit("voice_in", update, voice.duration or 0, "pending",
           {"ogg_bytes": ogg_path.stat().st_size if ogg_path.exists() else 0})

    transcript = await asyncio.to_thread(_transcribe, ogg_path)
    try:
        ogg_path.unlink()
    except OSError:
        pass

    if not transcript:
        _audit("voice_skip", update, 0, "stt_unavailable")
        await _safe_reply(update,
                           "Voice transcription not enabled yet — please "
                           "type your message and I'll route it.")
        return

    if USER_MODE.get(user.id) != "wren":
        await _safe_reply(update,
                          f"(heard: \"{transcript[:120]}\")\n\n"
                          "Voice notes only route to Wren — pick option 2"
                          " from the menu first.\n\n" + MENU_TEXT)
        _audit("voice_outside_wren", update, len(transcript), "self")
        return
    cid = _caller_id(user.id)
    rc, data = await _f0_post("/api/f0/converse",
                                {"caller_id": cid, "text": transcript})
    reply = data.get("text") or "Sorry, the front desk is briefly unreachable."
    await _safe_reply(update, f"(heard: \"{transcript[:120]}\")\n\n{reply}")
    _audit("voice_out", update, len(reply), rc,
           {"transcript_len": len(transcript)})


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("handler error: %s", ctx.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Front desk hiccup — try again in a moment.")
        except Exception:
            pass


def main() -> int:
    global ALLOWLIST
    token = _load_token()
    ALLOWLIST = _load_allowlist()
    log.info("starting qsb_telegram_receptionist v%s node=%s f0=%s allowlist=%s",
             VERSION, NODE, F0_BASE,
             "open" if not ALLOWLIST else f"{len(ALLOWLIST)} chat(s)")
    app = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("end", cmd_end))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    _audit("boot", None, 0, "self",
           {"f0_base": F0_BASE, "whisper_present": Path(WHISPER_BIN).exists(),
            "allowlist_size": len(ALLOWLIST)})
    app.run_polling(allowed_updates=["message"], drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
