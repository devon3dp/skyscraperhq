# IQUEST-CODER (40B local) — Curriculum

## Domain: production code review + gotcha detection

## Required skills
1. **Code review** — given 3 recent .py files, find ONE concrete gotcha each
2. **Format discipline** — output GOTCHA: <file:line> <issue> <fix>
3. **F47 stamp** — write review results to audit trail

## Pass bar
- Find non-obvious bug in 1 of 3 files ✓
- Output strict GOTCHA format ✓
- Stamp F47 ✓

## Tool
`tools/qsb_iquest_code_review.py` runs review against 3 most-recent tools/*.py
