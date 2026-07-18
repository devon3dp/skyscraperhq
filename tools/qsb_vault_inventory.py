#!/usr/bin/env python3
"""Vault inventory — R74_ALL_UNDERSTAND_THE_VAULT.

Gives HQ + TP + Acer + Wren a read-only INDEX of what lives in the vault so
they know which providers, keys, tokens, and receptionists are wired up.
Returns filenames + short description (derived from name) + byte size — NOT
raw secret values.

Usage:
  python3 tools/qsb_vault_inventory.py                   # human-readable
  python3 tools/qsb_vault_inventory.py --json            # machine
  python3 tools/qsb_vault_inventory.py --actor tp_pip    # journaled read

Every read journaled to data/registries/qsb_vault_inventory_reads.jsonl.
Actors: hq_claude, tp_pip, acer_cass, wren.
"""
import argparse, json, os, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VAULT = REPO / "floors" / "floor_28_security_department" / "vault"
JOURNAL = REPO / "data" / "registries" / "qsb_vault_inventory_reads.jsonl"

DESCRIPTIONS = {
    ".env.alpaca_paper":       "Alpaca paper-trading (stocks) — API key + secret",
    ".env.anthropic":          "Anthropic API key (Claude)",
    ".env.binance_testnet":    "Binance testnet (crypto) — API key + secret",
    ".env.cohere":             "Cohere API key (LLM)",
    ".env.deepseek":           "DeepSeek API key (LLM)",
    ".env.galaxy_sim":         "Samsung Galaxy SIM (Three UK unlimited) creds",
    ".env.gemini":             "Google Gemini API key (LLM)",
    ".env.gmail":              "Gmail SMTP/IMAP creds (app password blocked)",
    ".env.groq":               "Groq API key (fast inference)",
    ".env.kimi":               "Kimi (Moonshot) API key",
    ".env.namecheap":          "Namecheap DNS creds (domain mgmt)",
    ".env.netlify":            "Netlify deploy token",
    ".env.nighthawk":          "Netgear Nighthawk router admin",
    ".env.oanda_practice":     "OANDA practice-trading (forex) — token + account",
    ".env.openai":             "OpenAI API key",
    ".env.oracle_cloud":       "Oracle Cloud tenancy (remote VM)",
    ".env.outlook":            "Outlook/Hotmail SMTP creds",
    ".env.ross_profile":       "Ross profile data (name, address, DOB, etc)",
    ".env.skyscraper_ssh":     "SSH private key for cross-CEO access (vault key)",
    ".env.skyscraper_ssh.pub": "SSH public key (companion to skyscraper_ssh)",
    ".env.stripe":             "Stripe API key (payments)",
    ".env.sudo":               "Ross's sudo password (root elevation on HQ box)",
    ".env.telegram":           "Telegram bot token (receptionist channel)",
    ".env.twilio":             "Twilio Voice + SMS + WhatsApp Business creds",
}


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def journal(row):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    row.setdefault("ts", utc())
    with open(JOURNAL, "a") as f:
        f.write(json.dumps(row) + "\n")


def build_index():
    items = []
    for p in sorted(VAULT.iterdir()):
        if not p.is_file(): continue
        if p.name.startswith(".env.") and (".bak_" in p.name or p.name.endswith(".template")):
            continue
        if not p.name.startswith(".env."): continue
        items.append({
            "name": p.name,
            "size": p.stat().st_size,
            "description": DESCRIPTIONS.get(p.name, "(no description on file)"),
        })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--actor", default="hq_claude",
                    help="hq_claude, tp_pip, acer_cass, or wren")
    args = ap.parse_args()

    items = build_index()
    journal({"actor": args.actor, "op": "inventory_read", "count": len(items)})

    if args.json:
        print(json.dumps({"vault_path": str(VAULT), "items": items,
                          "count": len(items), "ts": utc(),
                          "actor": args.actor}, indent=2))
        return
    print(f"═══ VAULT INVENTORY — R74 (actor={args.actor}) ═══")
    print(f"  path: {VAULT}")
    print(f"  {len(items)} credentials/keys/configs available:")
    for it in items:
        print(f"    {it['name']:35s} {it['size']:>5}B  {it['description']}")


if __name__ == "__main__":
    main()
