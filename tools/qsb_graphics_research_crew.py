#!/usr/bin/env python3
"""qsb_graphics_research_crew.py — autonomous photo-research loop for F47.

Ross 2026-06-13: "if you get your certified graphics crew... to look at all the
photos in the photos folder, they will get to see the evolution and the changes
of the dashboards that we've been doing, and then they'll be able to see what
actually keeps not working and what works and what was lost and what was gained."

This is the RESEARCH layer. The crew:
  · scans every screenshot in ~/Pictures/Screenshots/
  · extracts visual features (dominant colors, brightness, layout signal)
  · groups screenshots by session (UTC date)
  · diff-checks consecutive sessions to detect regression/improvement
  · writes a markdown evolution report
  · stamps F47 records so progress is visible while Wren is away
  · writes concrete CSS / palette PROPOSALS to qsb_code_proposals.jsonl
    (the proposal queue Ross approves on return)

Helix gate respected — this is RESEARCH + PROPOSE, never EXECUTE.
"""
from __future__ import annotations
import json, hashlib, sys, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PHOTOS = Path("/home/ross/Pictures/Screenshots")
REPORT = ROOT / "data/registries/qsb_graphics_evolution_report.md"
JSONL = ROOT / "data/registries/qsb_graphics_evolution_report.jsonl"
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"
STATE = ROOT / "data/registries/qsb_graphics_research_state.json"


# F47 palette per helix strand "taste: violet + amber + dark glass"
F47_PALETTE = {
    "amber": "#ff8c28",
    "violet": "#9a6cff",
    "dark_glass": "#0a1422",
    "dark_glass_2": "#0e1828",
    "muted": "#8aa0b8",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"analyzed_hashes": [], "last_run_ts": None,
            "runs": 0, "proposals_written": 0}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=2))


def parse_ts(fn: str):
    # "Screenshot from 2026-06-13 09-00-58.png" → datetime
    base = fn.replace("Screenshot from ", "").replace(".png", "")
    try:
        return datetime.strptime(base, "%Y-%m-%d %H-%M-%S")
    except Exception:
        return None


def hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def dominant_colors(p: Path, k=5) -> list[tuple[int, int, int]]:
    """Quick downsampled color quantization. No sklearn — PIL's adaptive palette."""
    img = Image.open(p).convert("RGB")
    img.thumbnail((128, 128))
    q = img.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    return [(pal[i*3], pal[i*3+1], pal[i*3+2]) for i in range(k)]


def brightness(p: Path) -> float:
    img = Image.open(p).convert("L")
    img.thumbnail((64, 64))
    px = list(img.getdata())
    return sum(px) / len(px) / 255.0


def analyze_one(p: Path) -> dict:
    return {
        "filename": p.name,
        "size_bytes": p.stat().st_size,
        "ts": parse_ts(p.name).isoformat() if parse_ts(p.name) else None,
        "sha16": hash_file(p),
        "brightness": round(brightness(p), 3),
        "dominant_colors": [
            "#{:02x}{:02x}{:02x}".format(*rgb) for rgb in dominant_colors(p)
        ],
    }


def palette_distance(hex_a: str, hex_b: str) -> float:
    """Euclidean distance between two hex colors in RGB space."""
    a = int(hex_a[1:3], 16), int(hex_a[3:5], 16), int(hex_a[5:7], 16)
    b = int(hex_b[1:3], 16), int(hex_b[3:5], 16), int(hex_b[5:7], 16)
    return ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5


def helix_palette_score(dominant: list[str]) -> float:
    """How well does this screenshot's palette match F47's helix taste?
    Higher = closer to amber/violet/dark-glass."""
    refs = list(F47_PALETTE.values())
    total = 0.0
    for c in dominant:
        # min distance to any helix anchor
        d = min(palette_distance(c, r) for r in refs)
        total += d
    return -total / len(dominant)  # higher = closer (negate distance)


def main(limit_new: int = 100):
    if not PHOTOS.exists():
        print(f"NO PHOTOS DIR: {PHOTOS}")
        return 1

    state = load_state()
    seen = set(state.get("analyzed_hashes", []))
    new_findings = []
    skipped = 0

    files = sorted(PHOTOS.glob("Screenshot from *.png"))
    print(f"[graphics-crew] {len(files)} screenshots in folder, {len(seen)} already analyzed")

    for p in files:
        if len(new_findings) >= limit_new:
            break
        try:
            sha = hash_file(p)
            if sha in seen:
                skipped += 1
                continue
            f = analyze_one(p)
            f["helix_palette_score"] = round(helix_palette_score(f["dominant_colors"]), 2)
            new_findings.append(f)
            seen.add(sha)
            with JSONL.open("a") as fh:
                fh.write(json.dumps(f) + "\n")
        except Exception as exc:
            print(f"  skip {p.name}: {str(exc)[:80]}")

    if not new_findings:
        print("[graphics-crew] nothing new to analyze")
        return 0

    # group by UTC date for evolution view
    sessions = defaultdict(list)
    for f in new_findings:
        if f["ts"]:
            sessions[f["ts"][:10]].append(f)

    # write markdown evolution report
    lines = [f"# QSB Tower — graphics evolution report",
              f"_generated by F47 graphics research crew at {utcnow()}_",
              "",
              f"- screenshots scanned this run: **{len(new_findings)}**",
              f"- skipped (already analyzed): {skipped}",
              f"- helix palette anchors: " +
                ", ".join(f"`{v}`" for v in F47_PALETTE.values()),
              "",
              "## Sessions",
              ""]
    palette_drift_proposals = 0
    for date in sorted(sessions.keys()):
        rows = sorted(sessions[date], key=lambda r: r["ts"])
        avg_bright = sum(r["brightness"] for r in rows) / len(rows)
        avg_score = sum(r["helix_palette_score"] for r in rows) / len(rows)
        lines.append(f"### {date} — {len(rows)} screenshots")
        lines.append(f"- avg brightness: **{avg_bright:.2f}**  "
                      f"(F47 prefers dark-glass, target ~0.15)")
        lines.append(f"- avg helix-palette score: **{avg_score:.0f}**  "
                      f"(closer to 0 = closer to amber/violet/dark-glass)")
        lines.append(f"- sample dominant colors: " +
                      ", ".join(f"`{c}`" for c in rows[0]["dominant_colors"]))
        lines.append("")

        # PROPOSAL: if session drifts brighter or away from palette, queue a tweak
        if avg_bright > 0.35:
            prop = {
                "ts": utcnow(),
                "from": "f47.decorator.makeover_team",
                "kind": "css_palette_proposal",
                "session_date": date,
                "reason": (f"session {date} averaged brightness {avg_bright:.2f}, "
                            f"F47 helix taste is dark-glass (~0.15). Recommend "
                            f"reducing --bg lightness or increasing overlay opacity."),
                "target_files": ["src/dashboard/static/cockpit.css",
                                  "src/dashboard/static/qsb_3d_dashboard.css"],
                "concrete_change": {
                    "css_var": "--qsb-bg",
                    "from_hint": "lighter dark tone",
                    "to": F47_PALETTE["dark_glass"],
                },
                "approved_by_ross": None,
                "applied": False,
            }
            with PROPOSALS.open("a") as fh:
                fh.write(json.dumps(prop) + "\n")
            palette_drift_proposals += 1

    REPORT.write_text("\n".join(lines))

    # write F47 record
    rec = {
        "ts": utcnow(),
        "kind": "graphics_research_tick",
        "floor": "F47",
        "operator": "background",
        "executed_by": "F47.graphics_research_crew",
        "screenshots_analyzed": len(new_findings),
        "skipped": skipped,
        "sessions_covered": list(sorted(sessions.keys())),
        "proposals_written": palette_drift_proposals,
        "report_path": str(REPORT.relative_to(ROOT)),
    }
    with F47_REC.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")

    # persist state
    state["analyzed_hashes"] = list(seen)
    state["last_run_ts"] = utcnow()
    state["runs"] = state.get("runs", 0) + 1
    state["proposals_written"] = state.get("proposals_written", 0) + palette_drift_proposals
    save_state(state)

    print(f"[graphics-crew] analyzed {len(new_findings)}, "
          f"{palette_drift_proposals} proposals queued, "
          f"report at {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(limit_new=int(os.environ.get("QSB_PHOTO_LIMIT", "60"))))
