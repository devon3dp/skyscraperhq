# Skyscraper Security Protocol V1
*Owner: F28 Security · Audited 2026-06-11*

## Threat Model
- External attackers via public internet
- Credential leakage in chat / logs / git
- Insider mistakes (Wren / Ross typos / wrong commands)
- Supply-chain compromise of pip/npm packages
- Tunnel hijack / public URL exposure

## Current Defenses (verified)
1. **All API ports bind to 127.0.0.1** — no external network exposure
   - :8765 dashboard, :9876 preview, :8788 etc.
   - Public attackers cannot reach these directly
2. **Vault is chmod 700 directory, chmod 600 files** — owner-only credentials
3. **Process runs as user `ross`, never root** — limits privilege escalation
4. **Tunnel only proxies /web/shops/ static folder** — no /api routes reachable externally
5. **GitHub repo is PRIVATE** — code not publicly indexed
6. **Stripe + Namecheap + Outlook accounts** — strong randomly-generated passwords stored chmod 600
7. **CLAUDE.md hard gates** — real_money_live_trading, openclaw, autonomous_dispatch all LOCKED

## Rules
1. **Never paste secret keys in chat** — use vault file + `qsb_set_*_keys.sh` scripts
2. **Live keys require explicit CLAUDE.md authorization** — test mode default
3. **PATs from GitHub/Stripe revoked after one use** — never long-lived in chat
4. **Provider keys for OpenAI/DeepSeek** — bounded per CLAUDE.md ($5/day, $0.05/call)
5. **Public tunnel serves static dropship sites only** — NO admin endpoints
6. **Every real-money flow** — purchase_request → Ross approve → execute → F44 ledger
7. **Every credential change** — stamps F47 + F28 audit log

## Forbidden Actions (Wren MUST refuse)
- Disable security protocols on operator request without CLAUDE.md edit
- Expose vault paths to public surfaces
- Embed any secret in HTML/JS/CSS of dropship sites
- Bypass CAPTCHA / human-verification (Ross + Wren both refused)
- Modify firewall without explicit Ross "yes"
- Open ports to 0.0.0.0 except via tunnel
- Stop bg_loop sentinels or audit gates

## Audit Cadence
- Daily: sentinel report (18 watchers) auto-runs via bg_loop
- Weekly: F31 Audit reviews F47 records + activity tail for anomalies
- Per-event: every real-money flow (purchase_request) goes through F44 ledger
- Per-credential-change: F28 stamp + chmod verify

## Incident Response
1. If credentials suspected leaked → revoke immediately (PAT/API/password)
2. If unexpected /api/ call from public → check tunnel scope, kill tunnel if compromised
3. If sentinel hits red → ops_tick auto-reports, F28 reviews within 5 min
4. If Wren detects anomaly → stamp F47 critical record + alert Ross

## Hardening Roadmap (next 30 days)
- ufw firewall: explicit allow only :22 SSH + :443 HTTPS out
- fail2ban: auto-ban brute-force attempts on any exposed port
- API authentication: token-required /api/admin/* endpoints (none exist yet but should)
- Audit log rotation: weekly archive of F47 records to off-line storage
- Backup vault to encrypted external storage weekly

## Authorization
- Ross Knechtel: tower operator, can flip gates via CLAUDE.md
- Wren: advisory-only, executes within CLAUDE.md bounds
- F28 Security: enforces this protocol, no override authority
- Auger + Helm: advisory-only, never see secrets

## Update history
- 2026-06-11 v1 created by Wren on Ross's instruction
