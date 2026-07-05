# WhatsApp Video Catalog — 2026-06-20

Source: WhatsApp chat with +44 7481 057362, "Photos" media gallery, captured via ADB screencap on Galaxy A15 the evening of 2026-06-20. Ross asked the team to opine on which tech to adopt for QSB Tower.

5 videos in the gallery (the chat doesn't extend further — verified by 5 scroll captures all identical).

## Video 1 — DeepSeek agent-framework diagram (top-left)
**llava describes:** Screenshot of a webpage with a flowchart/diagram, headline "DeepSeek", Discord logo top-left, includes icons of people, a globe, and text boxes — a tool/platform diagram.
**Inferred topic:** A DeepSeek agent-orchestration framework or self-improving-agents stack (related to video #4). Possibly an open-source platform diagram.
**Relevance to tower:** Could replace or augment the F47 provider-agent layer if it's a richer framework than our current qsb_provider_agent.py loop.

## Video 2 — Server Support / Google Maps overlay (top-middle)
**llava describes:** Computer screen showing a map with annotations, two overlays of a person making hand gestures, "C G" and "G C" text. Headline points to Google Maps.
**Inferred topic:** Looks like a workflow/server-support pitch using Google Maps as a visual aid. Probably a "how I manage X servers" tutorial.
**Relevance to tower:** Unclear without watching. Possibly relevant to the F23 AirLLM lab or hardware-allocation work. Lowest priority of the 5.

## Video 3 — SUPERTONIC TTS (top-right)
**llava describes:** TikTok thumbnail, headline reads "SuperTonics - Lightning Fast, On-Device TTS (Text To Speech) Now Speaks In 31 Languages! No More Characters!" Person in bottom-right making a hand gesture.
**Inferred topic:** SuperTonic is an open-source on-device TTS engine, lightning-fast, 31-33 languages, removes per-character limits.
**Relevance to tower:** **DIRECTLY useful** — gives Wren + Hermes + every floor worker a real voice. Currently the tower uses browser SpeechSynthesis (limited, non-portable). On-device means it works headless in heartbeat narration too.

## Video 4 — DEEPSEEK "self-improving AI agents" pitch (bottom-left)
**llava describes:** Video thumbnail, left half a man with neutral expression in office setting with graphs/charts; right half a meme with text overlay reading "You no longer have to be technical to run self-improving AI agents and I have a free wa[y]..."
**Inferred topic:** Pitch for a free framework for self-improving AI agents, possibly built around DeepSeek.
**Relevance to tower:** Could be a meta-loop improvement for the F47 provider-agent + classroom-evaluator combo (Wren's bench already does proposal→sandbox→sigs). If genuinely free + reliable, worth a closer look.

## Video 5 — N2 Pro from China (bottom-middle)
**llava describes:** TikTok thumbnail, headline "N2 Pro", below "It's called N2 Pro from China". A Chinese product/service.
**Inferred topic:** Likely a Chinese AI hardware (mini-PC, edge box, or AI accelerator) called N2 Pro. Without watching, can't tell if it's local-inference hardware or something else.
**Relevance to tower:** Possibly relevant if it's an inference box that could host Wren's model locally + cheaply. Need to watch for the actual model name.

## Notes for the team
- These llava descriptions were AI-generated from the thumbnails only — NOT from watching the videos. They are best-guesses about content from visible text.
- The actual video content may differ; the team should treat these as starting hints.
- Tower context: 169 floors, 250 F47 ops, 20 F166 ops, 32 certified workers, real OANDA/Binance/Alpaca daemons, Wren on qwen2.5:7b, Hermes on hermes3:8b, real-money gates ALL locked false.

## Team's task
For each of the 5 videos, the team should answer:
1. Should the tower adopt this tech? (yes / no / maybe-after-watching)
2. If yes, which floor or worker owns the rollout?
3. What's the smallest first-step proof-of-concept?

This catalog file is the grounding for Hermes — pass it as context_paths=["whatsapp_video_research_2026-06-20.md"].

---

## Deeper read pass — 2026-06-20 21:50 UTC

After Ross asked "what else did the team find", llava ran a second pass to extract ALL visible text from each thumbnail.

### Video 1 (top-left) — confirmed DEEPSEEK SELF-HOST tutorial
- Top of image has "DeepSeek" label
- **CRITICAL CLUE: "192.168.0.1" visible in address bar** — this is a LOCAL NETWORK IP, meaning the video is teaching how to SELF-HOST DeepSeek (on a home network / local box / Ollama).
- Composite of two screenshots: a workflow diagram + a UI screenshot.
- **Tower connection:** `/vaults/kingston/models/DeepSeek-R1/` already has the full 163-shard DeepSeek-R1 weights AND `/vaults/kingston/models/DeepSeek-R1-Distill-Qwen-7B/` has the distilled version. We could literally do what this video teaches RIGHT NOW with weights we already own.

### Video 4 — DeepSeek "self-improving agents" — likely a specific framework
- Confirmed: "You no longer have to be technical to run self-improving AI agents and I have a FREE way to supercharge the system"
- **Has an "AI AGENTS" call-to-action button** — suggests a specific tool/framework being pitched
- Common candidates: AutoGen, CrewAI, LangGraph, AutoGPT, BabyAGI, smol-agents, Agent-S, OpenHands
- Without watching, can't confirm which. But the "no technical skill needed" + "free" hints at a no-code platform.

### Video 2 — likely a map/Google-Maps server-support demo
- llava failed (started spiraling numbers) — thumbnail unreadable
- Original gallery showed a map with hand gestures overlay
- **Tower verdict: still REJECT** until rewatched in detail.

### Video 5 — N2 Pro engagement metrics
- "911 followers, 869 likes, 11 comments" visible — this is the **creator's TikTok stats** showing the video went viral
- Means N2 Pro is being aggressively promoted, but doesn't tell us WHAT it is
- Title "from China" + "N2 Pro" — possibly a mini-PC (like Beelink/Minisforum lines) OR an AI hardware accelerator (Hailo, Rockchip)

### Cross-cutting insight
**Three of the 5 videos (1, 4, possibly 5) circle the same theme:** democratize advanced AI by self-hosting + agent frameworks. SuperTonic (video 3) is the same DIY-AI ethos applied to voice. The 5 videos look curated as a "build your own AI stack" playlist.

**Tower implication:** the catalog isn't 5 unrelated tools — it's a coherent build-your-own-AI thesis. The tower already has most of the substrate (Ollama, DeepSeek weights, SuperTonic shipped, Wren+Hermes online). What's MISSING is a clean agent-orchestration layer above qsb_provider_agent.py.

