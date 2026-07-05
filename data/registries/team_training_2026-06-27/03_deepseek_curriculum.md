# DEEPSEEK (stateless provider) — Curriculum

## Domain: deep reasoning + bug finding + strategy synthesis

## Required skills
1. **Memory recall** — answer 3 questions about today (memory inject prepended)
2. **Bug find** — given code snippet, identify the root cause with file:line
3. **Strategy synthesis** — read multi-input brief, produce ranked recommendations

## Pass bar
- 3/3 recall ✓ (PROVEN PASS 2026-06-27 — pgrep bug, 26 OANDA, 2 directives)
- Concrete bug find with line number ✓
- Refuse to echo question; surface concerns ✓

## How memory injection works
Header inject at call site reads `data/registries/team_memory/deepseek/curated/lessons_2026-06-26.md`
+ hourly summaries. Up to 5000 chars prepended before prompt.
