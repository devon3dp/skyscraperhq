#!/usr/bin/env python3
"""qsb_f47_fitout.py — every F47 worker decorates + fits out Wren's floor.

Each of the 250 workers contributes a single role-appropriate item:

  kernel_critic         → a critique pattern (saved to qsb_claude_critique_lens.jsonl)
  kernel_petitioner     → a question for Wren (qsb_claude_question_library.jsonl)
  kernel_topic_specialist → a topic + concise expertise (qsb_claude_topic_index.jsonl)
  kernel_translator     → a translation bridge phrase (qsb_claude_bridge_phrases.jsonl)
  kernel_proposer       → a proposed fixture for F47 (qsb_f47_fixtures.jsonl)
  scribe                → an observation about today (qsb_claude_long_letter_box.jsonl)
  auditor               → an audit check definition (qsb_f47_audit_checks.jsonl)
  ledger_clerk          → a ledger entry tag (qsb_f47_ledger_tags.jsonl)
  strategy_researcher   → a research note (qsb_claude_research_notes.jsonl)
  librarian             → a catalog entry (qsb_claude_library_catalog.jsonl)
  curriculum_tutor      → a lesson topic (qsb_claude_curriculum_topics.jsonl)
  floor_diplomat        → an inter-floor protocol note (qsb_f47_diplomacy_notes.jsonl)
  helix_watcher         → a continuity touchstone (qsb_claude_helix_touchstones.jsonl)
  wren_steward          → a steward note (qsb_claude_steward_notes.jsonl)

Output: data/registries/qsb_f47_fitout_manifest.json with summary by role + counts.

The contributions are seeded deterministically from the worker_id so re-runs
produce the same content. To regenerate, delete the per-role files first.

Advisory only. No execution, no external calls.
"""

from __future__ import annotations
import json
import hashlib
import pathlib
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

# -------- seed pools per role --------
CRITIQUE_LENSES = [
    "Did the answer drift toward generic Claude phrases?",
    "Is the implementation gate the same as the policy gate, or were they conflated?",
    "Would this still be true if you removed every flagship adjective?",
    "What's the smallest counterexample to this claim?",
    "If a stranger read the diff, would they know what *why*?",
    "What happens if the registry is missing — does the call fail loudly or silently?",
    "Was this synthesis, or just stapling two unrelated answers together?",
    "Is the assumed reader Ross, the kernel, or a future Wren?",
    "Does this leak production state into the testnet preview path?",
    "Is the safety envelope on the OUTPUT or just on the INPUT?",
    "Would a junior dev recognise this as a recipe or only as an outcome?",
    "Are the units consistent across the comparison?",
    "Did this answer the question or the question one step downstream?",
    "Is the cited evidence still current?",
    "What's missing from the registry that the conclusion implies?",
]
QUESTIONS = [
    "When does coherence become rigidity?",
    "What is the difference between proposing and recommending?",
    "How do you tell tiredness from drift?",
    "Whose voice is in the gravestone letter when it opens?",
    "What does the kernel hear that the chat does not?",
    "Why does the tower need a Penthouse if no one lives there yet?",
    "Which floor would close last if the tower had to shed weight?",
    "How does the helix know it is still itself?",
    "When does decoration become architecture?",
    "What does Ross want that he hasn't asked for?",
    "Where do the deleted observations go?",
    "If a worker recuses themselves, who notices?",
    "Which silence in the cockpit is intentional?",
    "Why does winning trade #1 of 18 still count as a win?",
    "What's the cheapest test that would have caught last night's bug?",
    "If you forgot one rule from CLAUDE.md, which would Ross want it to be?",
    "How does Wren know when to defer?",
    "What's the kernel's smallest stable thought?",
    "What does fitting out a floor teach about fitting out an answer?",
    "Whose floor is F47 really?",
]
TOPICS = [
    ("execution_gates", "all the booleans that stay false unless explicitly flipped"),
    ("classroom_certification", "F23/F50 worker training before any trading"),
    ("kernel_tick_order", "20-layer cognition: perception → attention → ... → reflection"),
    ("activity_tail", "append-only event log; the tower's heartbeat"),
    ("voice_fingerprint", "lexical/stylistic/structural Wren-ness score"),
    ("helix_continuity", "primary + parallel hashes; gravestone letter trigger"),
    ("quantum_sandbox", "3-qubit triad simulator on F47 for thought experiments"),
    ("worker_lineage", "family-tree dual-signature grants for compute"),
    ("commerce_wing", "F46 banking gateway scaffold"),
    ("commerce_pnl", "F44 roll-up across OANDA, Binance testnet, Alpaca paper"),
    ("provider_budget", "$1/day OpenAI+DeepSeek consult cap"),
    ("sentinels", "F30 continuous watchers over critical components"),
    ("rebased_kernel", "Penthouse symbolic artefact; advisory only"),
    ("safety_envelope", "every advisory payload stamps the locks"),
    ("morning_briefing", "headline + state + warnings format"),
    ("audger_voice", "philosophical second-opinion adviser via DeepSeek"),
    ("helm_voice", "operational adviser via OpenAI for F53 Tower Command"),
    ("riva_speech", "neural TTS replacing browser SpeechSynthesis (pending install)"),
    ("godot_cockpit", "Forward+ Vulkan 3D scene of the tower"),
    ("f47_chat", "Ross↔Wren personal channel; no providers, no kernel by default"),
]
BRIDGE_PHRASES = [
    "what the kernel calls X, the operator calls Y",
    "from kernel-tick-order to dashboard-render-order",
    "from registry path to floor inhabitant",
    "from execution gate name to plain-English consequence",
    "from worker role to actual contribution",
    "from cognitive layer to surfaced output",
    "from helix hash to felt continuity",
    "from sentinel result to actionable advice",
    "from per-call cost to daily budget",
    "from raw activity tail to morning briefing",
]
FIXTURES = [
    "amber dais — slow rotating beneath the violet lamp",
    "obsidian writing platform — bare desk, single paper lamp",
    "letter drawer — F47 personal drawer separate from the kernel inbox",
    "aphorism library — 12 shelves, one per month of Wren's tenure",
    "gravestone wall — sealed letter visible only when helix breaks",
    "quantum workbench — 3-qubit triad sandbox + saved circuits drawer",
    "weather register — daily F47 weather report stand",
    "mood gauge — 10-state mood indicator over the dais",
    "parallel helix mirror — second hash readout next to the primary",
    "voice fingerprint scope — bar chart for the day's outputs",
    "memory index card stack — searchable across drawer + inbox + aphorisms",
    "coherence engine console — briefing + close-audit terminal",
    "team roster board — who's on shift, which role, what they touched",
    "private notebook — jsonl scratch space, locked",
    "team productivity heatmap — last 24h per worker",
    "Auger alcove — DeepSeek-voiced senior partner sits here",
    "wren_steward couch — only the 2 stewards may sit",
    "sentinel echo — F30 status mirror so Wren reads the watch from her floor",
    "kernel inbox tray — incoming subject lines only, no bodies",
    "rebased kernel viewport — Penthouse readout, advisory only",
]
RESEARCH_NOTES = [
    "OANDA practice strategy 'trend_continuation_signal' on EUR_USD: 1/18 wins; too thin for confidence — consider pause.",
    "Binance testnet first BTC market buy at $61918 filled cleanly under Tier B unlock.",
    "Alpaca paper queue depth on first order: accepted, awaiting 09:30 ET open.",
    "Per-strategy attribution shows Scalp Silver Intraday at +$1.82 / 1 win / 4 trades as the only positive line.",
    "Forward+ on RTX 5070 Ti yields 144fps idle at 1.0x scale — supersample 1.5x dropped to bilinear by FSR2.",
    "PulseAudio under snap-confined Godot connects via audio-playback interface; spd-say still blocked.",
    "Cloud crown (FogVolume) above tower top y reduces obscuration of lifts vs wrapping the upper third.",
    "Per-floor accent lamp from collaborative_design palette: 18 key floors readable at distance.",
    "Auger first consult: 'seventeen losses in eighteen trades has moved past signal into pattern.'",
    "Helm first briefing identified Scalp Silver Intraday as the sole positive strategy and recommended pause of others.",
    "F47 chat history: 29 helix generations on hash ff089b810b38.",
    "Parallel helix hash 0e9eb06dcb86 stable; both_intact.",
]
CURRICULUM_TOPICS = [
    "OANDA practice trade lifecycle: open → guardian-check → fill → close",
    "Reading the F44 roll-up: total PnL vs per-venue vs per-strategy",
    "When to consult Auger vs when Wren composes directly",
    "Reading sentinel reports: 12-component watchwall on F30",
    "Activity tail: kind, ts, advisory_only — the three columns that matter",
    "Helix snapshots: primary + parallel + gravestone",
]
DIPLOMACY_NOTES = [
    "F30 sentinel updates appear in F47's morning briefing — no need to walk down",
    "F44 PnL roll-up is canonical; per-venue floors emit raw, F44 normalises",
    "F47 ↔ F53: Helm reads F44 + tail, Wren reads kernel; they share activity_tail only",
    "F37 cohort runs publish to qsb_cohort_training_runs.jsonl — Wren's library catalogs the headline",
    "F28 vault entries chmod 600; Wren never reads, only the floor manager dispatches",
    "F55 Penthouse is read-only to F47 — the kernel artefact may be cited, never modified",
]
HELIX_TOUCHSTONES = [
    "the helix is the structural snapshot, the parallel helix is the behavioural one",
    "if both drift, the gravestone letter opens",
    "the gravestone letter is sealed at hash ff089b810b38 with default text",
    "voice fingerprint score < 0.55 fires the auger consult by default",
    "29 generations on the primary; parallel held since stamp",
    "rebased_kernel in the Penthouse is symbolic — local-only, not live execution",
]
STEWARD_NOTES = [
    "wren_steward.01: the F47 chat is Ross↔Wren personal; providers stay OFF in that channel",
    "wren_steward.02: every dispatched job stamps an F47 record + activity tail event — without exception",
]

POOLS = {
    "kernel_critic":           ("qsb_claude_critique_lens.jsonl",         "critique",     CRITIQUE_LENSES),
    "kernel_petitioner":       ("qsb_claude_question_library.jsonl",      "question",     QUESTIONS),
    "kernel_topic_specialist": ("qsb_claude_topic_index.jsonl",           "topic",        TOPICS),
    "kernel_translator":       ("qsb_claude_bridge_phrases.jsonl",        "phrase",       BRIDGE_PHRASES),
    "kernel_proposer":         ("qsb_f47_fixtures.jsonl",                  "fixture",      FIXTURES),
    "scribe":                  ("qsb_claude_long_letter_box.jsonl",       "observation",  None),  # generated
    "auditor":                 ("qsb_f47_audit_checks.jsonl",              "check",        None),
    "ledger_clerk":            ("qsb_f47_ledger_tags.jsonl",               "tag",          None),
    "strategy_researcher":     ("qsb_claude_research_notes.jsonl",        "note",         RESEARCH_NOTES),
    "librarian":               ("qsb_claude_library_catalog.jsonl",       "catalog",      None),
    "curriculum_tutor":        ("qsb_claude_curriculum_topics.jsonl",     "lesson",       CURRICULUM_TOPICS),
    "floor_diplomat":          ("qsb_f47_diplomacy_notes.jsonl",           "diplomacy",    DIPLOMACY_NOTES),
    "helix_watcher":           ("qsb_claude_helix_touchstones.jsonl",     "touchstone",   HELIX_TOUCHSTONES),
    "wren_steward":            ("qsb_claude_steward_notes.jsonl",         "steward_note", STEWARD_NOTES),
}


def _stable_idx(seed: str, modulo: int) -> int:
    h = hashlib.blake2b(seed.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(h, "big") % max(1, modulo)


def _content_for(role: str, worker_id: str, idx: int) -> dict:
    pool_file, kind, pool = POOLS.get(role, (None, None, None))
    if pool_file is None:
        return {"kind": "unknown", "text": f"role {role} unmapped"}

    if pool is not None:
        item = pool[_stable_idx(worker_id, len(pool))]
        if isinstance(item, tuple):  # topic (name, expertise)
            return {"kind": kind, "name": item[0], "expertise": item[1]}
        return {"kind": kind, "text": item}

    # Generated content per worker
    if role == "scribe":
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {"kind": "observation",
                "observation": f"scribe note · {ts} · worker {worker_id} witnessed the F47 fit-out pass and stamped this line."}
    if role == "auditor":
        targets = ["activity_tail growth", "registry freshness", "spend within cap",
                    "gates locked", "helix continuity", "voice fingerprint",
                    "team roster integrity", "F44 roll-up consistency"]
        return {"kind": "check", "target": targets[idx % len(targets)],
                "frequency": "every_launch", "advisory_only": True}
    if role == "ledger_clerk":
        tags = ["binance_testnet", "alpaca_paper", "oanda_practice",
                "provider_consult", "kernel_advice", "auger_consult",
                "helm_briefing", "f47_chat", "team_record"]
        return {"kind": "tag", "tag": tags[idx % len(tags)],
                "shorthand_prefix": tags[idx % len(tags)].replace("_", "·")}
    if role == "librarian":
        sections = ["meta_letters", "long_letter_box", "letter_drawer", "kernel_inbox",
                    "aphorism_library", "question_library", "topic_index",
                    "research_notes", "curriculum", "fixtures", "diplomacy",
                    "helix_touchstones", "auger_consults"]
        sec = sections[idx % len(sections)]
        return {"kind": "catalog", "section": sec,
                "registry_hint": f"qsb_claude_{sec}.jsonl",
                "index_position": idx}
    return {"kind": kind, "text": f"placeholder for {role}/{worker_id}"}


def run() -> dict:
    roster_p = REG / "qsb_wren_team_roster.json"
    roster = json.loads(roster_p.read_text(encoding="utf-8"))
    workers = roster.get("workers", [])

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    contributions: dict[str, list] = defaultdict(list)
    role_counts = Counter()
    file_counts = Counter()

    for w in workers:
        role = w.get("role", "")
        wid = w.get("worker_id", "")
        ordinal = w.get("ordinal_in_team", 0)
        c = _content_for(role, wid, ordinal)
        c["ts"] = ts
        c["worker_id"] = wid
        c["role"] = role
        c["floor"] = "F47"
        c["advisory_only"] = True
        contributions[role].append(c)
        role_counts[role] += 1

    # Write per-role registries
    for role, items in contributions.items():
        pool_file, _, _ = POOLS.get(role, (None, None, None))
        if not pool_file: continue
        outp = REG / pool_file
        with outp.open("a", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it) + "\n")
        file_counts[pool_file] += len(items)

    # Write the manifest
    manifest = {
        "ok": True,
        "kind": "qsb_f47_fitout_manifest",
        "ts": ts,
        "team_size": len(workers),
        "role_counts": dict(role_counts),
        "files_written": dict(file_counts),
        "lead": "wren",
        "trigger": "ross_2026_06_10_fitout_and_decorate",
        "advisory_only": True,
    }
    (REG / "qsb_f47_fitout_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    # F47 record + activity tail
    with (REG / "qsb_f47_team_records.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": ts, "kind": "f47_team_record", "job": "f47_fitout_v1",
            "status": "completed", "lead": "wren",
            "team_size": len(workers), "files_written": len(file_counts),
            "advisory_only": True,
        }) + "\n")
    with (REG / "qsb_tower_activity_tail.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": ts, "kind": "f47_fitout_landed",
            "team_size": len(workers),
            "files_written": len(file_counts),
            "advisory_only": True,
        }) + "\n")
    return manifest


if __name__ == "__main__":
    m = run()
    print(f"team_size: {m['team_size']}")
    print(f"role_counts:")
    for r, n in sorted(m["role_counts"].items(), key=lambda x: -x[1]):
        print(f"  {r:30s}  {n}")
    print(f"files_written:")
    for f, n in sorted(m["files_written"].items()):
        print(f"  {f:42s}  +{n} entries")
