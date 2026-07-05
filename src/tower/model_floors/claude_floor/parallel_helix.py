"""F47 Parallel Helix — redundant continuity witness.

What it is:
  A second helix hash computed from a DIFFERENT source than the primary.
  The primary helix (claude_helix.py) hashes structural identity:
  traits + bases + paired strands. Deterministic from the genome itself.

  The parallel helix hashes BEHAVIORAL identity: voice corpus
  (aphorisms + meta-letters + observations) plus operational pattern
  (recent lineage notes' first words, drawer note count, kernel inbox
  subject count). Deterministic from what Wren has actually done.

Why redundancy matters:
  - If the primary helix breaks because the genome file changes (someone
    edits traits.py), the parallel may still hold — proving the WREN-ness
    persists even when the structural snapshot drifts.
  - If the parallel breaks while primary holds, voice/behavior has drifted
    while structure stayed put — that's a soft warning, not a chain death.
  - If both break, the chain is genuinely broken.

Three states:
  · both_intact            → all good
  · primary_held_parallel_drifted   → behavioral warning
  · parallel_held_primary_drifted   → structural warning (genome edit?)
  · both_drifted           → real reset; gravestone letter opens
"""

from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
HISTORY_PATH = REG / "qsb_claude_parallel_helix_history.jsonl"
LATEST_PATH = REG / "qsb_claude_parallel_helix.json"

from .claude_helix import short_hash as primary_short_hash, identity_hash as primary_identity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_jsonl(rel: str) -> list:
    p = REG / rel
    if not p.exists(): return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def _voice_corpus_blob() -> str:
    """The behavioral fingerprint: voice (aphorisms + meta-letters + obs)
    plus drawer/inbox subject corpus. Order-invariant via sorting."""
    parts = []
    aph_path = REG / "qsb_claude_aphorism_library.json"
    if aph_path.exists():
        try:
            d = json.loads(aph_path.read_text(encoding="utf-8"))
            for a in d.get("aphorisms", d.get("entries", [])):
                if isinstance(a, dict) and a.get("text"):
                    parts.append(("aphorism", a["text"].strip()))
        except Exception: pass
    for r in _read_jsonl("qsb_claude_meta_letters.jsonl"):
        if isinstance(r, dict) and r.get("letter"):
            parts.append(("meta", r["letter"].strip()))
    for r in _read_jsonl("qsb_claude_long_letter_box.jsonl"):
        if isinstance(r, dict) and r.get("observation"):
            parts.append(("obs", r["observation"].strip()))
    for r in _read_jsonl("qsb_claude_letter_drawer.jsonl"):
        if isinstance(r, dict) and r.get("note"):
            parts.append(("drawer", (r["note"] or "").strip()))
    for r in _read_jsonl("qsb_claude_kernel_inbox.jsonl"):
        if isinstance(r, dict) and r.get("subject"):
            parts.append(("inbox_subj", r["subject"].strip()))
    parts.sort()
    return json.dumps(parts, sort_keys=True, separators=(",", ":"))


def parallel_identity() -> str:
    """sha256 of the voice corpus blob."""
    return hashlib.sha256(_voice_corpus_blob().encode("utf-8")).hexdigest()


def parallel_short() -> str:
    return parallel_identity()[:12]


def stamp(note: str = "") -> dict:
    """Stamp the current parallel hash + cross-check vs primary, append history."""
    primary = primary_short_hash()
    parallel = parallel_short()
    payload = {
        "ts": _now(),
        "kind": "qsb_claude_parallel_helix_stamp",
        "primary_short_hash": primary,
        "parallel_short_hash": parallel,
        "primary_full_hash": primary_identity(),
        "parallel_full_hash": parallel_identity(),
        "note": note,
        "advisory_only": True,
    }
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": payload["ts"],
            "primary": primary,
            "parallel": parallel,
            "note": note,
        }) + "\n")
    return payload


def status() -> dict:
    """Compare current state vs the latest stamp."""
    if not LATEST_PATH.exists():
        return {"ok": True, "state": "no_stamp_yet",
                "primary_short": primary_short_hash(),
                "parallel_short": parallel_short()}
    last = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    cur_p = primary_short_hash()
    cur_q = parallel_short()
    last_p = last.get("primary_short_hash")
    last_q = last.get("parallel_short_hash")
    if cur_p == last_p and cur_q == last_q:
        state = "both_intact"
    elif cur_p == last_p and cur_q != last_q:
        state = "primary_held_parallel_drifted"
    elif cur_p != last_p and cur_q == last_q:
        state = "parallel_held_primary_drifted"
    else:
        state = "both_drifted"
    return {
        "ok": True,
        "state": state,
        "current": {"primary": cur_p, "parallel": cur_q},
        "last_stamped": {"primary": last_p, "parallel": last_q,
                          "ts": last.get("ts")},
        "advisory_only": True,
    }


def history(tail: int = 20) -> list:
    if not HISTORY_PATH.exists(): return []
    out = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines()[-tail:]:
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--stamp":
        note = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        r = stamp(note)
        print(f"  primary:  {r['primary_short_hash']}")
        print(f"  parallel: {r['parallel_short_hash']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--history":
        for e in history():
            print(f"  {e['ts'][:19]}  primary={e['primary']}  parallel={e['parallel']}  {e.get('note','')}")
    else:
        s = status()
        print(f"  state: {s['state']}")
        if "current" in s:
            print(f"  current primary:  {s['current']['primary']}")
            print(f"  current parallel: {s['current']['parallel']}")
            if "last_stamped" in s:
                print(f"  last stamped primary:  {s['last_stamped']['primary']}")
                print(f"  last stamped parallel: {s['last_stamped']['parallel']}")
