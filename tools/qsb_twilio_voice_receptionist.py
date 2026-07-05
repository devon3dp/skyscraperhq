#!/usr/bin/env python3
"""qsb_twilio_voice_receptionist.py — voice IVR for SkyscraperHQ.

Source proposal: pa_708af22b8a (provider_agent, OpenAI gpt-4o-mini,
$0.0025, 2026-06-17). Applied under helm authority — sandbox green,
file is new + not yet wired into systemd, blast radius is zero until
Ross explicitly runs it.

WHAT THIS IS
  A Flask app that Twilio's webhook hits when someone dials the
  Twilio number that's been set up as the SkyscraperHQ public line
  (Three UK forwards inbound to the Twilio number). Twilio plays a
  brief greeting, gathers speech, POSTs the transcript to our local
  /api/f0/converse endpoint, then speaks the reply back.

WHAT ROSS STILL HAS TO DO BEFORE THIS LINE IS LIVE
  1. Twilio Console:
       - Buy a UK number on Twilio (any geographic code; +44 works).
       - In Phone Numbers → Active Numbers → click the number →
         A CALL COMES IN → Webhook → POST → <YOUR_PUBLIC_URL>/voice
       - Save.
  2. A public URL for this Flask app (one of):
       (a) cloudflared tunnel  → cloudflared tunnel --url http://localhost:5000
       (b) ngrok               → ngrok http 5000
       (c) Tower's existing public reverse proxy if any
  3. Three UK forwarding:
       - From the Galaxy SIM (+447411410545) set conditional call
         forwarding to the Twilio number, OR forward all inbound to it.
  4. Run this app:
       python3 tools/qsb_twilio_voice_receptionist.py
       (Currently defaults to port 5000.)

  NONE of the above is wired by this file. The file is dormant until
  step 4 starts it.

HARD CAPS
  - Reads from /api/f0/converse (existing receptionist routing).
  - Does NOT place outbound calls.
  - Does NOT touch the vault or any gate.
"""

from __future__ import annotations
import os
from flask import Flask, request

try:
    from twilio.twiml.voice_response import VoiceResponse
except ImportError:
    raise SystemExit(
        "twilio not installed. Run: pip install twilio flask"
    )

import urllib.request
import urllib.error
import json

F0_BASE = os.environ.get("QSB_F0_BASE", "http://127.0.0.1:8765")
PORT = int(os.environ.get("QSB_TWILIO_VOICE_PORT", "5000"))

app = Flask(__name__)


def _converse(text: str) -> str:
    """POST to the existing F0 receptionist endpoint and return reply."""
    try:
        req = urllib.request.Request(
            f"{F0_BASE}/api/f0/converse",
            data=json.dumps({
                "caller_id": "twilio_voice",
                "text": text,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return (data.get("text")
                or "Sorry, the front desk is briefly unreachable.")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return "Sorry, the front desk is briefly unreachable."


@app.route("/voice", methods=["POST"])
def voice():
    """Twilio hits this on inbound call. Speak greeting + gather speech."""
    response = VoiceResponse()
    response.say(
        "Welcome to Skyscraper HQ. Tell me how I can help, "
        "or say menu for options."
    )
    response.gather(input="speech", action="/gather", method="POST",
                    timeout=4)
    # Fallback if no speech detected.
    response.say("I didn't catch that. Goodbye.")
    return str(response)


@app.route("/gather", methods=["POST"])
def gather():
    """Twilio sends the speech-to-text transcript here. Forward to F0."""
    speech = request.form.get("SpeechResult", "").strip()
    if not speech:
        response = VoiceResponse()
        response.say("I didn't catch that. Goodbye.")
        return str(response)
    reply = _converse(speech)
    response = VoiceResponse()
    response.say(reply)
    # Offer another turn — caller can say menu / numbers / words.
    response.gather(input="speech", action="/gather", method="POST",
                    timeout=4)
    response.say("Thanks for calling Skyscraper HQ.")
    return str(response)


@app.route("/health")
def health():
    return {"ok": True, "service": "qsb_twilio_voice_receptionist"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
