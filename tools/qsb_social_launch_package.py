#!/usr/bin/env python3
"""qsb_social_launch_package.py — stage Skyscraper HQ social accounts.

Ross 2026-06-12: "get the IT team to open Instagram + TikTok accounts".

CLAUDE.md hard-locks web_access_autonomous_enabled = false. Workers cannot
open external accounts. The IT team can only PREPARE the package. Ross opens
the accounts manually at instagram.com / tiktok.com / instagram.com/business.

This tool produces:
  · brand kit (handle, bio, link tree, colors)
  · 7-day post calendar with theme, CTA, hashtags
  · 3 ready-to-post drafts (with prompt for image to attach)
  · explicit "what Ross has to do" checklist
  · safety stamp confirming no autonomous account creation
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def _now():
    return datetime.now(timezone.utc).isoformat()


BRAND = {
    "company_name": "Skyscraper HQ",
    "tagline": "Eighteen shops, one tower.",
    "preferred_handle": "@skyscraperhq",
    "alt_handles": ["@hqskyscraper", "@skyhq.shops", "@skyscraperhq_uk"],
    "bio_short": "QSB Tower V1.5 · 18 storefronts on 165 floors · Beauty · Tech · Pets · Outdoor · Wellness · UK",
    "bio_tiktok": "Eighteen shops. One tower. We post the prep, the pricing, and the picks.",
    "link_tree": [
        {"label": "Shop catalog",   "url": "https://qsb-tower-shops.example/"},
        {"label": "Lumen chat AI",  "url": "https://qsb-lumen.example/"},
        {"label": "Tower cockpit",  "url": "https://qsb-tower.example/cockpit"},
    ],
    "brand_colors": {
        "primary":  "#ffd76b",  # tower gold
        "accent":   "#b08aff",  # penthouse purple
        "ink":      "#dfeaff",
        "bg":       "#070d1a",
    },
    "logo_concept": "Glowing penthouse halo over a vertical tower silhouette",
}


CALENDAR_TEMPLATE = [
    {"theme": "Tower-of-shops tour",
     "image_prompt": "Hero shot of the 18-floor shop ring — neon teal/orange/gold zone bands",
     "caption_template": "18 shops, one tower. Welcome to Skyscraper HQ. {handle}",
     "hashtags": ["#SkyscraperHQ", "#UKShops", "#OnlineShopping"],
     "cta": "tap link in bio · today's pick is the F61 brightening serum"},
    {"theme": "F61 · Lumière Beauty walkthrough",
     "image_prompt": "Flat-lay of Vitamin C Serum, Jade Roller, Hyaluronic Moisturiser",
     "caption_template": "Three skincare picks from the F61 floor. {handle}",
     "hashtags": ["#Skincare", "#Vitamins", "#Beauty"],
     "cta": "shop F61 — link in bio"},
    {"theme": "F65 · Vector Tech daily driver",
     "image_prompt": "Compact gadget on a slate desk, soft window light",
     "caption_template": "F65 Vector Tech — honest spec, no marketing fluff. {handle}",
     "hashtags": ["#Tech", "#Gadgets", "#UK"],
     "cta": "see the spec sheet — link in bio"},
    {"theme": "F63 · Pawsworth — for the four-legged household member",
     "image_prompt": "Dog napping on a memory-foam bed in soft golden light",
     "caption_template": "F63 Pawsworth picks. Vet-tested, easy to clean. {handle}",
     "hashtags": ["#Pets", "#DogsOfInstagram", "#CatsOfInstagram"],
     "cta": "F63 catalog — link in bio"},
    {"theme": "Behind the scenes · How the tower picks its stock",
     "image_prompt": "Dark dashboard screen with 165 floor labels, gold penthouse halo",
     "caption_template": "Margin math, ledger checks, classroom-trained sourcing. {handle}",
     "hashtags": ["#Behindthescenes", "#Retail", "#UKBusiness"],
     "cta": "watch the build — link in bio"},
    {"theme": "F154 · Trailhead Outdoor weekend kit",
     "image_prompt": "Lightweight rucksack and weatherproof jacket on a wet stile",
     "caption_template": "Built for a UK weekend. F154 Trailhead Outdoor. {handle}",
     "hashtags": ["#Outdoor", "#Hiking", "#UKHikes"],
     "cta": "F154 — link in bio"},
    {"theme": "Operator Q&A · How we test before we trade",
     "image_prompt": "Cockpit 3D tower at twilight with traders standing on F41-45",
     "caption_template": "Every trader passes the classroom before they place. {handle}",
     "hashtags": ["#FinTech", "#Trading", "#PaperTrading"],
     "cta": "DM your question — we'll answer in stories"},
]


def _calendar(start_day=None):
    start = start_day or datetime.now(timezone.utc).date()
    out = []
    for i, post in enumerate(CALENDAR_TEMPLATE):
        d = start + timedelta(days=i)
        row = dict(post)
        row["date"] = d.isoformat()
        row["day_of_week"] = d.strftime("%A")
        out.append(row)
    return out


DRAFTS = [
    {
        "platform": "instagram",
        "draft_for_date": (datetime.now(timezone.utc).date()).isoformat(),
        "kind": "feed_post",
        "caption": ("18 shops, one tower.\n\n"
                    "Skyscraper HQ is QSB Tower V1.5 — a 165-floor advisory "
                    "AI building running 18 storefronts on its commerce "
                    "floors. From Lumière Beauty on F61 to Maker Lane on "
                    "F163, every catalog is sourced, margin-checked and "
                    "served by trained staff.\n\n"
                    "Welcome. Tap the link in bio.\n\n"
                    "#SkyscraperHQ #UKShops #OnlineShopping #Curated"),
        "image_brief": "Hero render of the tower at twilight, penthouse halo glowing, 18 shop floors visible. 1080×1350. Bottom: 'SKYSCRAPER HQ' wordmark in tower gold.",
    },
    {
        "platform": "tiktok",
        "draft_for_date": (datetime.now(timezone.utc).date()).isoformat(),
        "kind": "vertical_video",
        "caption": ("18 shops in 1 tower 🏙️ #SkyscraperHQ\n\n"
                    "Today: skincare from floor 61.\n"
                    "Tomorrow: tech from floor 65.\n"
                    "Drop floor numbers — we'll tour them."),
        "video_brief": "20s vertical reel. Open on the 3D cockpit camera zooming up the tower. Floor 61 highlights orange. Cut to a flat-lay of the 3 F61 skincare picks. Voiceover: scripted from the caption. Outro: tower logo with 'link in bio'.",
    },
    {
        "platform": "instagram",
        "draft_for_date": ((datetime.now(timezone.utc).date()) + timedelta(days=1)).isoformat(),
        "kind": "carousel",
        "caption": ("F61 · Lumière Beauty · three picks under £20.\n\n"
                    "1. Vitamin C Brightening Serum 30ml · £14.99\n"
                    "2. Jade Roller + Gua Sha Set · £12.99\n"
                    "3. Hyaluronic Acid Daily Moisturiser · £18.99\n\n"
                    "Sourced via AliExpress · dropship · 7-day lead time.\n\n"
                    "#Skincare #UKBeauty #Vitamins"),
        "image_brief": "3 cards, 1080×1080 each. Card 1: Vitamin C serum. Card 2: Jade roller. Card 3: Moisturiser pot. Same lighting, tower-gold accent strip on each.",
    },
]


CHECKLIST_FOR_ROSS = [
    {"step": 1,
     "what": "Confirm handle availability",
     "where": "instagram.com/skyscraperhq + tiktok.com/@skyscraperhq",
     "if_taken": f"Fall back to one of: {', '.join(BRAND['alt_handles'])}",
     "automatable": False, "reason": "ToS requires human acceptance"},
    {"step": 2,
     "what": "Open Instagram business account",
     "where": "instagram.com → Sign up → Business",
     "needs": ["working email (knechtelross@gmail.com fine?)",
                "phone for 2FA",
                "business category: Retail",
                "bio text (see brand_kit.bio_short)"],
     "automatable": False, "reason": "Email + phone verification"},
    {"step": 3,
     "what": "Open TikTok for Business account",
     "where": "ads.tiktok.com or tiktok.com → Sign up → For Business",
     "needs": ["same email + phone",
                "business category: E-commerce / Retail",
                "bio text (see brand_kit.bio_tiktok)"],
     "automatable": False, "reason": "Email + phone verification"},
    {"step": 4,
     "what": "Link both accounts back to this tool",
     "where": "Tell Wren the URLs you got and the screenshot of the verify steps",
     "automatable": False, "reason": "Wren stamps F47 record with the actual handles"},
    {"step": 5,
     "what": "Post draft #1 (Instagram hero) using the image_brief",
     "where": "Instagram → New post → upload hero render",
     "automatable": "advisory-only", "reason": "Tower can generate caption + hashtags; Ross posts"},
]


def main():
    pkg = {
        "ok": True,
        "kind": "qsb_social_launch_package_v1",
        "generated_ts": _now(),
        "policy": ("Tower stages everything; account creation is Ross-only "
                   "because web_access_autonomous_enabled=false in CLAUDE.md "
                   "and ToS verification requires a human."),
        "brand_kit": BRAND,
        "calendar_7_day": _calendar(),
        "drafts_ready": DRAFTS,
        "ross_checklist": CHECKLIST_FOR_ROSS,
        "safety_envelope": {
            "real_account_creation_attempted": False,
            "web_access_autonomous_enabled": False,
            "execution_allowed": False,
            "advisory_only": True,
            "tower_will_NOT_attempt_account_creation": True,
        },
        "next_action": ("Ross: walk through ross_checklist[step 1..3] and "
                         "report the handles back. Wren stamps F47 + adds "
                         "the URLs to brand_kit.link_tree."),
    }
    out = ROOT / "data/registries/qsb_social_launch_package.json"
    out.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    print(f"social launch package staged → {out.relative_to(ROOT)}")
    print(f"  brand handle: {BRAND['preferred_handle']}")
    print(f"  calendar:     {len(pkg['calendar_7_day'])} days planned")
    print(f"  drafts ready: {len(DRAFTS)}")
    print(f"  ross checklist: {len(CHECKLIST_FOR_ROSS)} steps (all manual)")
    return pkg


if __name__ == "__main__":
    main()
