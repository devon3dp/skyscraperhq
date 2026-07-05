# NVIDIA Riva — Install & Wire-Up for Wren's Voice

**Status:** scaffolded 2026-06-10. Server endpoint + cockpit JS are live; falls back to browser SpeechSynthesis until Riva is reachable.

You (Ross) have an NVIDIA Developer account, an RTX 5070 Ti (16 GB VRAM, Blackwell), driver 580.159.04. All Riva prerequisites are satisfied. The steps below are the *manual* parts only Claude can't do for you.

---

## 1 · NGC API key

1. Sign in at https://ngc.nvidia.com
2. Top-right avatar → **Setup → Generate API Key**
3. Copy the key (you only see it once)
4. Save it to the Floor 28 vault (chmod 600):

```bash
echo 'NGC_API_KEY=<paste here>' > /vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.ngc
chmod 600 /vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.ngc
```

(The vault is already gitignored.)

---

## 2 · Docker + NVIDIA container toolkit

Quick check whether you already have them:

```bash
which docker && docker --version
which nvidia-ctk && nvidia-ctk --version
```

If either is missing:

```bash
# Docker
sudo apt update && sudo apt install -y docker.io
sudo usermod -aG docker $USER && newgrp docker

# NVIDIA container toolkit (so containers can use the RTX 5070 Ti)
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify GPU is visible inside containers:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

You should see the RTX 5070 Ti listed.

---

## 3 · Riva TTS NIM (x86 workstation path)

> **Correction (2026-06-10):** Earlier draft of this section pointed to the
> legacy `riva_quickstart` SDK bundle. Per current NVIDIA docs, that route is
> now **L4T/Jetson embedded only**. The x86 workstation path is the
> **Riva NIM containers** (Riva TTS NIM, Riva ASR NIM, Riva NMT NIM) —
> single-purpose Docker containers under the `nim/nvidia` org on NGC. Audit
> trail: dispatch records `kernel_critic.09/10` (OpenAI + DeepSeek
> researchers) confirmed the org path. The image tag below may have moved
> since this was written — verify on NGC before pulling.

Riva TTS NIM is a single container that bundles the TTS Triton server + the
default Magpie / FastPitch voices and exposes both gRPC (50051) and HTTP (9000).

### a. Authenticate to NGC from Docker

```bash
# Source the API key you saved in step 1
source /vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.ngc

# Log into NGC's container registry
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
```

### b. Pull + run the container

```bash
# Verify the current image tag on the NGC catalog page before pulling:
#   https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/riva-tts
# Then export it:
export RIVA_TTS_IMAGE="nvcr.io/nim/nvidia/riva-tts:<paste-current-tag>"

# Persistent model cache so models aren't re-downloaded every container start
mkdir -p ~/.cache/riva-tts-nim

docker run -d \
  --name riva-tts \
  --gpus all \
  --shm-size=8g \
  --restart unless-stopped \
  -e NGC_API_KEY="$NGC_API_KEY" \
  -v ~/.cache/riva-tts-nim:/opt/nim/.cache \
  -p 50051:50051 \
  -p 9000:9000 \
  "$RIVA_TTS_IMAGE"
```

**First-time start downloads ~10–15 GB of model weights.** Subsequent starts
read from the cache and are fast.

### c. Wait for ready

```bash
# Tail the logs until you see "Server started" / "all models READY"
docker logs -f riva-tts
# Ctrl-C once it's serving.
```

The gRPC endpoint is then live at `localhost:50051`, which is what the
`tools/qsb_riva_voice.py` wrapper and `/api/voice/wren` already point to.

### d. (Optional) Also pull Riva ASR NIM later

When you want microphone speech-to-text quality to match the TTS quality
(replacing the browser SpeechRecognition mic button), pull the matching
ASR container and expose it on a separate port:

```bash
export RIVA_ASR_IMAGE="nvcr.io/nim/nvidia/riva-asr:<current-tag>"
docker run -d --name riva-asr --gpus all --shm-size=8g \
  -e NGC_API_KEY="$NGC_API_KEY" \
  -v ~/.cache/riva-asr-nim:/opt/nim/.cache \
  -p 50052:50051 -p 9001:9000 \
  "$RIVA_ASR_IMAGE"
```

Tracked as future work; not wired into the cockpit yet.

---

## 4 · Install the Python client (one-time)

```bash
pip install nvidia-riva-client
```

(Pure Python wrapper; no GPU needed for this part.)

---

## 5 · Verify Wren can use it

```bash
cd /vaults/nvme0/qsb_tower_v1
python3 tools/qsb_riva_voice.py "Wren reporting from floor forty-seven."
```

Expected output when Riva is up:
```
[riva] reachable check: {'ok': True, 'uri': 'localhost:50051'}
[riva] ok=True voice=English-US.Female-1 sr=44100 bytes=<some>
[riva] wav written: /tmp/wren_riva_smoke.wav
```

Play it back: `aplay /tmp/wren_riva_smoke.wav`

Then in the cockpit dashboard, open the F47 chat — the voice picker should show **🎙️ Wren (NVIDIA Riva · neural)** as the default. Click Talk and you'll hear Riva.

---

## 6 · How it falls back

If Riva is down, stopped, or the gRPC port isn't listening, the cockpit silently falls back to browser SpeechSynthesis with the same Wren-preferred English female voice. You don't lose anything — Wren just sounds the way she always did.

The dashboard logs the fallback:
- Server: returns HTTP 503 with `{"fallback": "browser_speechsynthesis"}`
- Browser: catches `!resp.ok` and routes to `SpeechSynthesisUtterance`

To force-test the fallback, just `docker stop riva-speech` or `pkill -f riva_server`.

---

## 7 · Stopping / starting Riva later

```bash
docker stop riva-tts        # stops the container
docker start riva-tts       # starts it again (cache stays warm)
docker logs --tail 40 riva-tts   # peek at status
```

Riva TTS NIM idles around 3–4 GB VRAM with a small CPU footprint when not
actively synthesizing. The `--restart unless-stopped` flag in the run
command means it comes back up after reboots automatically — leave it
running. To remove entirely: `docker rm -f riva-tts`.

---

## 8 · What's NOT changed

- No execution gate flips. Riva is local TTS, not model inference. None of `worker_execution_enabled`, `provider_execution_enabled`, `live_dispatch_enabled` etc. move.
- No external provider calls. Riva runs entirely on your RTX 5070 Ti.
- No autonomous dispatch. The voice endpoint only fires when the cockpit JS POSTs to it (user-triggered Talk button or auto-speak-Wren toggle).

---

## 9 · Files touched on the QSB side

| File | Change |
|------|--------|
| `tools/qsb_riva_voice.py` | New — Python wrapper around the Riva gRPC client; LINEAR_PCM → WAV |
| `src/dashboard/server.py` | New `/api/voice/wren` POST endpoint; returns `audio/wav` or 503 |
| `src/dashboard/static/cockpit.js` | F47 voice picker: Riva first, browser fallback; `speakAsWren()` re-routes |
| `data/registries/qsb_riva_install_guide.md` | This file |

---

## 10 · Voice options (after install)

Riva TTS NIM ships several pretrained voices. List them by hitting the
REST endpoint exposed at port 9000:

```bash
curl -s http://localhost:9000/v1/audio/voices | python3 -m json.tool
```

Or via the gRPC client:

```bash
python3 -c "
import riva.client
auth = riva.client.Auth(uri='localhost:50051')
tts = riva.client.SpeechSynthesisService(auth)
print(tts.list_voices())
"
```

Common choices (verify against the actual list output):
- `English-US.Female-1` (default in the wrapper) — clear, neutral, broadcast-quality
- `English-US.Male-1`
- `English-US-FastPitch.Female` (FastPitch + HiFi-GAN; slightly different timbre)
- `Magpie-TTS-Multilingual` (newer multilingual voice; covers en/es/fr/de/zh)

To change Wren's default voice, edit `DEFAULT_VOICE` in `tools/qsb_riva_voice.py`,
or pass `{"voice": "..."}` in the `/api/voice/wren` POST body — the cockpit
voice picker already does this per-selection.

---

*Stamped to activity tail under `riva_install_guide_v1`.*
