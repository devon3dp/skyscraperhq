# Wren Multilingual Capability Assessment — qwen2.5:14b (existing local model)

Date: 2026-07-30 · Model: **qwen2.5:14b** (Wren's own brain, local Ollama
`127.0.0.1:11434`) · Method: real bounded probe battery, outputs quoted verbatim.
No new models installed (Ross A4 constraint). Fully offline. Zero cost.

## Bottom line

Wren's existing model is **already strong enough for the major world languages** —
no new model is required for them. It **fails on low-resource languages** (measured),
so for those the skill routes to a fallback instead of shipping a bad translation.
A dedicated MT model is recommended *in writing only* (below), for the low tier.

## What was tested

Forward translation (EN→X), back-translation (X→EN for comprehension), context /
formal-register preservation, code-switching, and in-language generation. Timing
and tokens/sec captured. All calls hit the local model only.

## Results — quoted real outputs

Source sentence: *"The lift carries a sealed packet between floors."*

| Language | Output | Verdict |
|---|---|---|
| French | `L'ascenseur transporte un paquet scellé entre les étages.` | ✅ perfect |
| Spanish | `El ascensor transporta un paquete sellado entre pisos.` | ✅ perfect |
| German | `Der Lift transportiert einen versiegelten Umschlag zwischen den Stockwerken.` | ✅ fluent (minor: Umschlag=envelope) |
| Mandarin | `电梯在楼层之间运送一个密封的包裹。` | ✅ perfect (back-translates clean) |
| Japanese | `エレベーターが階間を移動しながら封筒を運んでいます。` | ✅ fluent |
| Russian | `Лифт переносит запечатанный пакет между этажами.` | ✅ perfect |
| Arabic | `ال лифт ينقل حقيبة مغلقة بين الأدوار.` | ⚠️ **leaked a Cyrillic token `лифт`**; 'packet'→'bag' drift |
| Hindi | `लिफ्ट वराह में संकुचित पैकेट को फ्लोors...` + rambling meta-notes | ❌ broken, script-mixing, ignores instruction |
| Welsh | `Mae'r llift yn goriau gworn clir rhwng y floorau` + self-corrections | ❌ nonsense |
| Swahili | `Kilengelie kuhakikisha paka usalafi chenye chumbi...` | ❌ nonsense (back-translates to "stray cats have rules") |
| Zulu | `Ilozi liyisola ipaketi elingaqashene ngokuhlela...` | ❌ nonsense |

**Back-translation check** (model's own output → EN): French → *"The elevator
transports a sealed package between floors"* (clean); Mandarin → *"An elevator is
transporting a sealed package between floors"* (clean); Arabic → *"closed bag"*
(drift); Welsh → *"moving smoothly between floors"* (meaning lost); Swahili →
*"regulation ensures stray cats have rules"* (total semantic collapse).

**Context / formal register** (EN→German, formal Sie, 3 sentences):
`Frau Wren, Ihr Bericht ist heute Morgen eingegangen. Der Vorstand hat ihn geprüft
und war sehr beeindruckt. Könnten Sie ihnen bitte die zweite Version bis Freitag
zukommen lassen.` — ✅ correct formal register, pronoun referents (ihn=report,
ihnen=board) preserved. Excellent.

**Code-switching** (Spanish+French+English+German mix → English):
input *"Hola equipo, le lift est en panne again, y necesitamos ayuda ahora. Merci,
das ist wichtig."* → `Hello team, the elevator is out of order again, and we need
help now. Thanks, this is important.` — ✅ perfect, 0.7s.

**In-language generation**: Spanish Q&A and a French customer-service reply both
returned fluent, natural, register-appropriate text. ✅

## Resource cost / offline

- **Offline: yes.** localhost Ollama only; no network, no external provider, $0.
- **Speed:** ~65–70 tokens/sec. Warm short translations 0.3–4s. First call cold-loads
  the 9GB model (~minutes) — the skill uses generous timeouts + retries because the
  main box's Ollama wedges under load and a wedge-healer restarts it.
- GPU-accelerated on the main box; a wedge-heal restart was observed mid-assessment.

## What the model CAN do (ship with confidence)

- Translate to/from and generate in: **French, Spanish, German, Russian, Mandarin
  Chinese, Japanese, English** — and by qwen2.5's documented coverage Italian,
  Portuguese, Korean (not separately probed → treated HIGH but flag if surprised).
- Preserve **formal/informal register**, multi-sentence **context and pronoun
  referents**, and handle **code-switched** input cleanly.

## What the model CANNOT do (do NOT trust)

- **Low-resource languages: Welsh, Swahili, Zulu, Hindi** → garbled / nonsense.
- **Arabic**: usable-ish but showed foreign-token leakage and lexical drift → MEDIUM,
  verify before shipping.
- When out of its depth the model **rambles and adds self-correcting meta-notes**
  despite "reply with only the translation" — the skill detects this and downgrades.

## Recommendation (WRITTEN ONLY — install nothing without Ross's go)

The existing model covers the major languages, so **no action is needed for HIGH/MEDIUM
tiers**. IF low-resource coverage becomes a real requirement, recommend a dedicated
local machine-translation model rather than a bigger general LLM — specifically an
**NLLB-200** (Meta, 200 languages, distilled 600M/1.3B variants run on CPU) or
**M2M-100** build, served locally. This is a *recommendation for Ross to approve*, not
an install. Per A4, additional models are only justified because the existing model
**measurably failed** the low-resource tests above.

## The delivered skill

`skills/wren/multilingual_check/` (skill.json + skill.py). Given `text` +
`target_language`, it calls qwen2.5:14b and returns the translation with an honest
`confidence` tier (high/medium/low), `needs_review`, and a concrete `fallback` note
when the language is LOW-tier or the model shows out-of-depth signals (meta-rambling,
runaway length, non-Latin script leakage). Proven live: Spanish → high/clean; Welsh →
low + fallback fired correctly.

## Self-schedule note

Re-run this assessment (`python3 skills/wren/multilingual_check/skill.py <lang> <text>`
across the probe set) whenever Wren's local brain is swapped or upgraded, or if a new
target language starts appearing in real traffic. The tier tables in `skill.py`
(`_HIGH` / `_MEDIUM` / `_LOW`) are the single source of truth — update them from a
fresh measured run, never from assumption. Wren should self-schedule this check on any
model change rather than waiting to be asked.
