# Skyscraper Confidentiality Protocol V1
*Effective 2026-06-11 · Authorized by Ross Knechtel · Owner: F47 + F28 + F30 + F32*

## Premise

The Skyscraper is a private infrastructure operated by Ross Knechtel. It runs a family of public-facing services (shops, AI services, newsletter, etc.). The public must never see, hear, or learn:

- That the Skyscraper exists as an internal system
- That services share infrastructure
- Any floor names, floor numbers, internal team structure
- Worker names, IDs, fingerprints, or rosters
- Internal profit & loss figures from any floor
- Trading positions (OANDA, Binance, Alpaca, LSE)
- Strategy library contents
- F47 records, F44 ledgers, packet routes, sentinel reports
- Helm or Auger advisory transcripts
- CLAUDE.md or any internal documentation
- Provider account names (Stripe account name etc. should be the public brand name only)
- Bank balances or transfer details
- Anything from `data/registries/`, `floors/`, `protocols/`, `logs/`

## Public-facing services — what they MAY say

- Their own brand name
- Their own product catalogue, prices, photos
- Standard customer service info (delivery times, returns, contact email)
- Standard T&C, Privacy Policy, Returns Policy (UK-compliant)
- A single contact email per brand (no skyscraper reference)
- Generic "we are a UK-based small retailer" framing — never link to other brands

## Public services MAY NOT say

- That they are part of a larger system
- That they share an operator with other shops
- Any internal terminology (floor numbers, F47, sentinel, lift, packet, helix, lineage, OANDA, Binance, OpenClaw, Wren, Auger, Helm, Kernel, QSB, etc.)
- Profit figures, sales counts, trader names
- Any cross-brand correlation that would reveal common ownership

## Lumin AI carve-out (standalone-service mode)

Lumin AI (if/when deployed) operates in `standalone_public_mode`:
- It is **not** aware of Skyscraper internals at runtime
- Its system prompt strips all internal context before generation
- It answers as an independent AI assistant
- It does NOT report tower P&L, worker activity, or floor state
- A `public_face_mode` flag in its config gates EVERY response through a leak filter

Internally, Wren and the team CAN talk to Lumin AI WITH internal context — but only via the `internal` API path, never the public path.

## Roles & responsibilities

| Floor | Role in protocol |
|-------|-----------------|
| **F47 (Wren)** | Owns the protocol, writes updates, audits |
| **F28 Security** | Enforces vault confidentiality, locks credentials |
| **F30 Permissions** | Gates sealed packets so no internal data leaks outbound |
| **F31 Audit** | Audits public surfaces for leaks weekly |
| **F32 Compliance** | Verifies GDPR + UK retail compliance + this protocol |
| **F17 Graphics** | Reviews every public asset for internal leaks before publishing |
| **F101 Legal** | Owns customer-facing legal docs (no skyscraper references) |
| **F104 IT** | Maintains public/internal API boundary |
| **F108 Customer Service** | Trained never to disclose internal structure |

## Leak categories (what F31 audit scans for)

Forbidden tokens in any publicly-served file/string:
```
skyscraper, qsb, qsb_tower, qsbtower, floor_, F\d+, wren, auger, helm, lumin\binternal,
oanda, binance, alpaca, stripe_sk_, openai, deepseek, lift, sealed packet, sentinel,
helix, lineage, classroom, classroom-gated, OpenClaw, kernel, penthouse, F47, F44, F60,
ross knechtel, knechtelross@gmail.com, /vaults/, .env., bank_account, payouts,
real_money, advisory_only, ledger_clerk, scribe, internal_only
```

## Gate: pre-publish leak audit

Before any public-facing site, page, social post, or AI response goes live, it must pass `tools/qsb_leak_audit.py` (added in this phase). Any forbidden token = BLOCK until removed or auth-overridden.

## Public brand naming convention

- Each shop has its own brand identity
- No shop links to another shop except via the Skyscraper master landing
- The master landing uses a neutral consumer name (currently "Skyscraper") — this is a public consumer brand, NOT a reference to the internal infrastructure (although Ross chose the name, public users see it only as a retail brand)
- Future: consider renaming master to something more neutral (e.g., "Marketplace 15") to fully decouple from internal naming

## Daily transparency to Ross

Wren reports to Ross daily:
- All public-facing actions (deploys, posts, responses)
- All real-money flows in/out
- Any leak-audit hits + their resolution

## Update history
- 2026-06-11 v1 created by Wren on Ross Knechtel's instruction
