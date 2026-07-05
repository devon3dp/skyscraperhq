"""Tower Studio SVG graphics generator.

Produces real .svg files for the portfolio + hero. The "graphics
designer" worker role is conceptual; the geometric output is
deterministic + stylised. Files are written into the studio's web
asset directory so the live site serves them at /portfolio/*.svg
and /static/hero.svg.

Each generator takes a brand brief (palette + motif) and emits a
concept poster ~ 800x600.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import hashlib
import math


WEB_ROOT = Path("/vaults/nvme0/qsb_tower_v1/web/tower_studio")
PORTFOLIO_DIR = WEB_ROOT / "portfolio"
STATIC_DIR = WEB_ROOT / "static"


@dataclass
class Brief:
    slug: str
    company_name: str
    palette: List[str]      # e.g. ["#7d4f2e", "#ece5d9", "#1a1d23"]
    motif: str              # 'fox' | 'owl' | 'mountain' | 'tower'
    headline: str


CONCEPTS: List[Brief] = [
    Brief(slug="concept_bayreach",
           company_name="Bayreach Books",
           palette=["#7d4f2e", "#ece5d9", "#c79271", "#1a1d23"],
           motif="fox",
           headline="Stories with teeth."),
    Brief(slug="concept_nightowl",
           company_name="Night Owl Cafe",
           palette=["#1c2540", "#f3e7c8", "#a08350", "#fff7e1"],
           motif="owl",
           headline="Coffee, after dark."),
    Brief(slug="concept_apexgear",
           company_name="Apex Gear",
           palette=["#2c3e2d", "#d9e2c6", "#8a8f6a", "#1a1d23"],
           motif="mountain",
           headline="Built for the climb."),
]


def _hash_seed(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


# ── motif renderers (return SVG path snippets) ──────────────────
def _motif_fox(seed: int) -> str:
    # Stylised fox face
    return '''
      <g transform="translate(400,260)">
        <path d="M -120,-80 L 0,-150 L 120,-80 L 100,40 L 0,90 L -100,40 Z"
              fill="#7d4f2e" stroke="#1a1d23" stroke-width="3"/>
        <polygon points="-90,-100 -50,-30 -110,-50" fill="#7d4f2e" stroke="#1a1d23" stroke-width="2"/>
        <polygon points="90,-100 50,-30 110,-50" fill="#7d4f2e" stroke="#1a1d23" stroke-width="2"/>
        <ellipse cx="-40" cy="-10" rx="8" ry="12" fill="#1a1d23"/>
        <ellipse cx="40" cy="-10" rx="8" ry="12" fill="#1a1d23"/>
        <polygon points="-12,30 12,30 0,55" fill="#1a1d23"/>
      </g>'''


def _motif_owl(seed: int) -> str:
    return '''
      <g transform="translate(400,260)">
        <ellipse cx="0" cy="0" rx="120" ry="140" fill="#a08350" stroke="#1a1d23" stroke-width="3"/>
        <circle cx="-45" cy="-30" r="38" fill="#fff7e1" stroke="#1a1d23" stroke-width="3"/>
        <circle cx="45" cy="-30" r="38" fill="#fff7e1" stroke="#1a1d23" stroke-width="3"/>
        <circle cx="-45" cy="-30" r="14" fill="#1c2540"/>
        <circle cx="45" cy="-30" r="14" fill="#1c2540"/>
        <polygon points="-12,5 12,5 0,30" fill="#f3e7c8" stroke="#1a1d23" stroke-width="2"/>
        <path d="M -120,-130 L -90,-80 M 120,-130 L 90,-80"
              stroke="#1a1d23" stroke-width="4" fill="none"/>
      </g>'''


def _motif_mountain(seed: int) -> str:
    return '''
      <g transform="translate(0,360)">
        <polygon points="100,0 240,-200 380,40 280,40" fill="#2c3e2d" stroke="#1a1d23" stroke-width="2"/>
        <polygon points="320,40 460,-160 600,40 500,40" fill="#8a8f6a" stroke="#1a1d23" stroke-width="2"/>
        <polygon points="500,40 640,-220 800,40" fill="#2c3e2d" stroke="#1a1d23" stroke-width="2"/>
        <polygon points="220,-160 240,-200 260,-160" fill="#fff" />
        <polygon points="440,-130 460,-160 480,-130" fill="#fff" />
        <polygon points="620,-190 640,-220 660,-190" fill="#fff" />
        <circle cx="700" cy="80" r="38" fill="#d9e2c6"/>
      </g>'''


def _motif_tower(seed: int) -> str:
    return '''
      <g transform="translate(400,300)">
        <rect x="-50" y="-200" width="100" height="280" fill="#ece5d9" stroke="#1a1d23" stroke-width="3"/>
        <rect x="-50" y="-200" width="100" height="40" fill="#7d4f2e"/>
        <rect x="-30" y="-150" width="14" height="14" fill="#1a1d23"/>
        <rect x="-10" y="-150" width="14" height="14" fill="#1a1d23"/>
        <rect x="10" y="-150" width="14" height="14" fill="#c79271"/>
        <rect x="-30" y="-110" width="14" height="14" fill="#c79271"/>
        <rect x="-10" y="-110" width="14" height="14" fill="#1a1d23"/>
        <rect x="10" y="-110" width="14" height="14" fill="#1a1d23"/>
        <rect x="-30" y="-70" width="14" height="14" fill="#1a1d23"/>
        <rect x="-10" y="-70" width="14" height="14" fill="#c79271"/>
        <rect x="10" y="-70" width="14" height="14" fill="#1a1d23"/>
      </g>'''


_MOTIFS = {
    "fox": _motif_fox,
    "owl": _motif_owl,
    "mountain": _motif_mountain,
    "tower": _motif_tower,
}


def _generate_concept(brief: Brief) -> str:
    seed = _hash_seed(brief.slug)
    motif_fn = _MOTIFS.get(brief.motif, _motif_tower)
    bg = brief.palette[1] if len(brief.palette) > 1 else "#f5f1ea"
    ink = brief.palette[-1] if brief.palette else "#1a1d23"
    accent = brief.palette[0] if brief.palette else "#7d4f2e"
    # Decorative dots — deterministic
    dots = []
    for i in range(28):
        x = (seed + i * 911) % 800
        y = ((seed * 7) + i * 313) % 460
        r = ((seed + i) % 4) + 2
        dots.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{accent}" opacity="0.18"/>')
    dots_svg = "\n        ".join(dots)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="800" height="600" role="img" aria-label="{brief.company_name} concept">
  <defs>
    <linearGradient id="bg-{brief.slug}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{bg}"/>
      <stop offset="1" stop-color="{accent}" stop-opacity="0.15"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="800" height="600" fill="url(#bg-{brief.slug})"/>
  {dots_svg}
  {motif_fn(seed)}
  <text x="60" y="60" fill="{ink}" font-family="Georgia, 'Times New Roman', serif"
        font-size="40" font-weight="700">{brief.company_name}</text>
  <text x="60" y="100" fill="{ink}" font-family="Georgia, 'Times New Roman', serif"
        font-size="22" opacity="0.75">{brief.headline}</text>
  <text x="60" y="555" fill="{ink}" font-family="ui-sans-serif, system-ui, sans-serif"
        font-size="13" letter-spacing="3" opacity="0.55">TOWER STUDIO · CONCEPT · {brief.slug.upper()}</text>
</svg>
'''


def _generate_hero() -> str:
    # Abstract architectural composition — the Tower silhouette + lifts
    return '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600" aria-label="QSB Tower stylised silhouette">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ece5d9"/>
      <stop offset="1" stop-color="#f5f1ea"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="600" height="600" fill="url(#sky)"/>

  <!-- distant towers -->
  <rect x="40" y="380" width="40" height="200" fill="#cbc2b1" opacity="0.7"/>
  <rect x="92" y="340" width="40" height="240" fill="#cbc2b1" opacity="0.6"/>
  <rect x="500" y="360" width="40" height="220" fill="#cbc2b1" opacity="0.7"/>
  <rect x="552" y="320" width="40" height="260" fill="#cbc2b1" opacity="0.6"/>

  <!-- main tower -->
  <rect x="220" y="80" width="160" height="500" fill="#ece5d9" stroke="#1a1d23" stroke-width="3"/>
  <!-- penthouse cap -->
  <rect x="220" y="60" width="160" height="32" fill="#7d4f2e"/>
  <polygon points="220,60 300,16 380,60" fill="#7d4f2e" stroke="#1a1d23" stroke-width="3"/>

  <!-- floor strip -->
  <g fill="#c79271" stroke="#1a1d23" stroke-width="1">
    ''' + "\n    ".join(
        f'<rect x="232" y="{ 110 + i*35 }" width="136" height="2"/>'
        for i in range(12)
    ) + '''
  </g>

  <!-- windows -->
  ''' + "\n  ".join(
      f'<rect x="{ 244 + (j*22) }" y="{ 120 + i*35 }" width="14" height="22" fill="{("#1a1d23" if (i*5+j) % 4 else "#c79271")}"/>'
      for i in range(11)
      for j in range(6)
  ) + '''

  <!-- lift shaft glyph (left) -->
  <line x1="210" y1="120" x2="210" y2="560" stroke="#7d4f2e" stroke-width="3"/>
  <circle cx="210" cy="200" r="6" fill="#7d4f2e"/>
  <circle cx="210" cy="400" r="6" fill="#7d4f2e"/>

  <!-- ground line -->
  <line x1="0" y1="580" x2="600" y2="580" stroke="#1a1d23" stroke-width="3"/>

  <!-- "Tower Studio" tag -->
  <text x="220" y="610" font-family="ui-sans-serif, system-ui, sans-serif"
        font-size="14" fill="#4c5666" letter-spacing="3">FLOOR 49 · TOWER STUDIO</text>
</svg>
'''


def generate_all_assets() -> Dict[str, str]:
    """Write hero.svg + all portfolio concepts. Returns mapping
    relative-path → bytes-written."""
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    out: Dict[str, str] = {}
    hero_path = STATIC_DIR / "hero.svg"
    hero_path.write_text(_generate_hero(), encoding="utf-8")
    out["static/hero.svg"] = str(hero_path)
    for brief in CONCEPTS:
        path = PORTFOLIO_DIR / f"{brief.slug}.svg"
        path.write_text(_generate_concept(brief), encoding="utf-8")
        out[f"portfolio/{brief.slug}.svg"] = str(path)
    return out
