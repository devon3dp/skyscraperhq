# CLAUDE.md amendment draft — Authenticated CLI authorization

Drafted by Wren 2026-06-12 at Ross's request for the secretary role.

---

```
================================================================================
2026-06-12 Ross authorization — named authenticated CLI tools:

The following CLIs are authorized for autonomous invocation by Wren/workers
provided their authentication step was completed by Ross at least once:

  - netlify-cli         (after `netlify login` by Ross)
  - gh                  (after `gh auth login` by Ross)
  - stripe-cli          (after `stripe login` by Ross)
  - namecheap-cli       (after API token saved to vault by Ross)

Operational bounds:
  - autonomous_web_browsing remains FALSE — only these named CLIs
  - any command that costs money (paid deploys, domain renewals,
    Stripe charges, server upgrades) requires a separate "Ross: confirm"
    response or a per-call --confirm flag
  - every CLI invocation writes an `authenticated_cli_call` event to
    data/registries/qsb_tower_activity_tail.jsonl with the tool, the
    subcommand, the exit code, and the cost (if any)
  - vault credentials remain at chmod 600 in
    floors/floor_28_security_department/vault/
  - workers cannot rotate their own CLI tokens — Ross does that

Use cases authorized:
  - netlify-cli:   deploys, site creation, env var management, domain link
  - gh:            repo read/write for the project, PR creation
  - stripe-cli:    listing products/prices, webhook setup (test mode by default)
  - namecheap-cli: DNS record management for owned domains

NOT authorized:
  - any CLI not in this list
  - any command that opens a non-CLI browser flow (autonomous OAuth flows
    are still blocked — Ross does the OAuth dance)
  - using these tools to flip other locked gates
================================================================================
```

**To apply:** copy the block above into `/vaults/nvme0/qsb_tower_v1/CLAUDE.md` immediately after the existing `2026-06-10 Ross authorization — bounded external provider consultation` section. Save the file. The amendment takes effect on the next session start (memory loads at session boot).

**Reason for the draft path:** Wren shouldn't edit CLAUDE.md autonomously — the contract review is Ross's job. Wren can stage the text; Ross paste-and-saves.
