# WREN-fast (qwen3.5:9b) — Curriculum

## Domain: design + audit + local-codebase reasoning

## Required skills
1. **Memory recall** — answer 3 questions about today's events from curated lessons file
2. **Tool use** — invoke `wren_retrieve` to find specific file content
3. **Audit task** — find ONE concrete bug in given code snippet (push back, don't echo prompt)
4. **Design task** — propose ONE concrete UI improvement with file:line where to add it

## Pass bar
- 3/3 recall ✓
- Find concrete bug ✓ (not generic advice)
- Propose design with file path ✓

## Tools you have
- `wren_read_file` — read any file (SAFETY_DENY blocks vault/CLAUDE.md)
- `wren_retrieve` — semantic search over codebase
- `wren_propose_patch` — queue a patch to bench for multi-sig review
- `wren_stamp_f47` — log your work to F47 audit trail
