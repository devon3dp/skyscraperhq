# Skyscraper Email Architecture V1
*Effective 2026-06-11 · Owner: F164 Email Ops · Vault: F28 · Compliance: F32*

## Goals

- Each of the 15 shops + the master Skyscraper landing has its OWN public email address
- All 16 emails route into ONE central inbox
- The skyscraper (Wren + F164) reads, triages, replies on all 16 aliases
- No customer ever sees Ross's personal email — but it can be the underlying inbox
- Cost: £0 today, upgrade path documented

## Three tiers (cheapest first)

### Tier 0 — Gmail plus-addressing (£0, today)
Use Ross's existing or a new dedicated Gmail account.
Each shop's "email" is `<masterinbox>+<shop_slug>@gmail.com`.

Example with `skyscraper.london@gmail.com` as master:
| Shop | Public email |
|------|--------------|
| Lumière Beauty | skyscraper.london+lumiere@gmail.com |
| Pinwheel Toys | skyscraper.london+pinwheel@gmail.com |
| Pawsworth | skyscraper.london+pawsworth@gmail.com |
| Hearthstone Kitchen | skyscraper.london+hearthstone@gmail.com |
| Vector Tech | skyscraper.london+vector@gmail.com |
| Trailhead Outdoor | skyscraper.london+trailhead@gmail.com |
| Stretch Fitness | skyscraper.london+stretch@gmail.com |
| Quilltree Office | skyscraper.london+quilltree@gmail.com |
| Voyage & Co | skyscraper.london+voyage@gmail.com |
| Greenhouse Lane | skyscraper.london+greenhouse@gmail.com |
| Little Robin | skyscraper.london+littlerobin@gmail.com |
| Inkwell & Co | skyscraper.london+inkwell@gmail.com |
| Twilight Wellness | skyscraper.london+twilight@gmail.com |
| Living Light Eco | skyscraper.london+livinglight@gmail.com |
| Maker Lane | skyscraper.london+maker@gmail.com |
| Master | skyscraper.london@gmail.com |

All mail arrives in the same inbox. Gmail filters auto-label by the `+tag`.

### Tier 1 — Custom domain + email forwarding (~£8/yr)
Buy a domain. Add Cloudflare Email Routing (free) or ImprovMX free tier.

| Shop | Public email |
|------|--------------|
| Lumière Beauty | hello@lumiere-beauty.skyscraper.shop |
| ... | ... |

All forward to the master inbox.

### Tier 2 — Google Workspace (~£5/user/mo)
Real Gmail-style mailboxes per brand. Looks fully professional, full Google features.
Skip for now — too expensive until revenue justifies.

## What Wren needs (Gmail API access)

For autonomous read + reply, Wren needs OAuth2 credentials from a Google Cloud project:
1. Ross creates a Google Cloud project (free)
2. Enable Gmail API
3. Create OAuth2 client credentials
4. Add `OAUTH_CLIENT_ID` + `OAUTH_CLIENT_SECRET` to vault/.env.google
5. Ross runs `python3 tools/qsb_google_oauth_setup.py` — opens browser, Ross grants access, refresh token saved to vault

Scopes requested:
- `gmail.readonly` (read inbox)
- `gmail.send` (reply on his behalf)
- `gmail.modify` (label, archive)
- (NOT `gmail.delete` — too dangerous)

## F164 inbound pipeline (every 5 min via bg_loop)

```
1. POLL — Gmail API list new threads since last_seen_id
2. CLASSIFY — F164 Inbox Triage Clerks tag each thread:
              order_confirm | customer_enquiry | return_request | spam | marketing | other
3. AUTO-REPLY — F164 Auto-Reply Composer drafts a response from templates
4. CONFIDENTIALITY — F164 Confidentiality Gate runs qsb_leak_audit on draft
5. SEND — Gmail API send-as alias matching the original inbound
6. ESCALATE — anything classified "complex" goes to F108 Customer Service queue
7. ARCHIVE — full thread + responses written to qsb_email_log.jsonl
8. STAMP — F47 record + F44 if it's an order
```

## Confidentiality enforcement on outbound

Every outbound mail must:
- Use ONLY the public brand name (no skyscraper internals)
- NEVER reference floor numbers, sentinel, Wren, internal tools, etc.
- Pass qsb_leak_audit before send
- Be signed only with the brand name + customer support contact

## Setup steps for Ross

1. **Create a new Gmail** (or use existing): `skyscraper.london@gmail.com` (or your choice)
   - https://accounts.google.com/signup
   - Phone verification (use 07481057362 if needed)
   - **Add a profile** with name "Skyscraper Customer Care"
2. **Optional** but recommended: set up auto-forwarding rules
   - Gmail → Settings → Filters → label by +tag
3. **For Wren autonomous read**: create Google Cloud project + OAuth (steps in qsb_google_oauth_setup.py)

I'll update the 15 shop websites with their respective +alias emails as soon as you tell me the master Gmail handle.

## Update history
- 2026-06-11 v1 created by Wren (F47) on Ross Knechtel's instruction
