#!/usr/bin/env bash
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$RUN_ROOT/${STAMP}_ROSS_RULEBOOK_EXPORT"
REPORT="$OUTDIR/ALL_RULEBOOKS_AND_RULES_READOUT.txt"
FILELIST="$OUTDIR/rulebook_file_list.txt"

mkdir -p "$OUTDIR" "$SEND"

echo "============================================================" > "$REPORT"
echo "ROSS SKYSCRAPERHQ RULEBOOK EXPORT" >> "$REPORT"
echo "Generated: $(date -Is)" >> "$REPORT"
echo "Root: $ROOT" >> "$REPORT"
echo "============================================================" >> "$REPORT"
echo "" >> "$REPORT"

echo "Finding rulebook/rule/council/CEO/governance files..." | tee -a "$REPORT"

find "$ROOT" \
  -path "$ROOT/.venv" -prune -o \
  -path "$ROOT/node_modules" -prune -o \
  -path "$ROOT/__pycache__" -prune -o \
  -type f \( \
    -iname "*rule*" -o \
    -iname "*rulebook*" -o \
    -iname "*council*" -o \
    -iname "*governance*" -o \
    -iname "*ceo*" -o \
    -iname "*law*" -o \
    -iname "*policy*" -o \
    -iname "*doctrine*" -o \
    -iname "*charter*" \
  \) \
  \( \
    -iname "*.md" -o \
    -iname "*.txt" -o \
    -iname "*.json" -o \
    -iname "*.jsonl" -o \
    -iname "*.yaml" -o \
    -iname "*.yml" -o \
    -iname "*.py" -o \
    -iname "*.html" \
  \) \
  | sort > "$FILELIST"

echo "" >> "$REPORT"
echo "============================================================" >> "$REPORT"
echo "RULEBOOK FILES FOUND" >> "$REPORT"
echo "============================================================" >> "$REPORT"
cat "$FILELIST" >> "$REPORT"

echo "" >> "$REPORT"
echo "============================================================" >> "$REPORT"
echo "RULE-LIKE LINES FOUND ACROSS PROJECT" >> "$REPORT"
echo "============================================================" >> "$REPORT"

grep -RIn --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=__pycache__ \
  -E "R[0-9]+|rule|Rule|RULE|must|Must|MUST|shall|Shall|SHALL|forbidden|banned|cannot|can't|not allowed|Task Council|CEO|sign.?off|verify|verifier|solo|mimic|identity|Town Square|manuscript|proof|violation|override|Wren|Claude HQ|TP|Acer" \
  "$ROOT" \
  2>/dev/null \
  | head -2000 >> "$REPORT" || true

echo "" >> "$REPORT"
echo "============================================================" >> "$REPORT"
echo "FULL CONTENTS OF RULEBOOK-LIKE FILES" >> "$REPORT"
echo "============================================================" >> "$REPORT"

while IFS= read -r f; do
  [ -f "$f" ] || continue
  echo "" >> "$REPORT"
  echo "------------------------------------------------------------" >> "$REPORT"
  echo "FILE: $f" >> "$REPORT"
  echo "------------------------------------------------------------" >> "$REPORT"

  size="$(wc -c < "$f" 2>/dev/null || echo 0)"
  if [ "$size" -gt 300000 ]; then
    echo "[Large file: $size bytes. Showing first 400 lines and rule-like matches.]" >> "$REPORT"
    echo "" >> "$REPORT"
    sed -n '1,400p' "$f" >> "$REPORT" || true
    echo "" >> "$REPORT"
    echo "[Rule-like matches in large file]" >> "$REPORT"
    grep -nEi "R[0-9]+|rule|must|shall|forbidden|banned|cannot|not allowed|Task Council|CEO|sign.?off|verify|solo|mimic|identity|proof|violation" "$f" >> "$REPORT" || true
  else
    cat "$f" >> "$REPORT" || true
  fi
done < "$FILELIST"

echo "" >> "$REPORT"
echo "============================================================" >> "$REPORT"
echo "ROSS HARDENING NOTES TO CHECK TOMORROW" >> "$REPORT"
echo "============================================================" >> "$REPORT"
cat >> "$REPORT" <<'NOTES'

These are the rule areas to check against the existing rulebook:

1. No solo work.
2. No solo code writing.
3. No self-signoff.
4. No mimic authority.
5. Ask, don't do.
6. Teach, don't overwrite.
7. Respect each CEO's mind and home.
8. Research before claiming a task.
9. Idea review before Task Council admission.
10. Two sign-offs before an idea becomes a task.
11. Task Council task ID required before work.
12. Independent verifier proof required before closure.
13. Town Square post required for important work.
14. Manuscript hard-copy record required for important decisions.
15. CEO local truth reporting required.
16. No hidden hardware/device assumptions.
17. Violation creates a Task Council violation task.
18. Receptionist is not a CEO.
19. Wren boundary is protected.
20. Tour Guide must be production-grade, live, interactive, and not a placeholder.

Tomorrow's job:
Do not replace the rulebook.
Read it first.
Find shallow rules.
Add hardening clauses underneath them.
Do not contradict existing rules.
Make every rule define:
- meaning
- scope
- allowed behaviour
- banned bypasses
- proof required
- violation response
- override authority

NOTES

cp -a "$REPORT" "$SEND/LATEST_RULEBOOK_EXPORT.txt"
cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"

echo ""
echo "DONE."
echo "Rulebook export written to:"
echo "$REPORT"
echo ""
echo "Send this file back to ChatGPT:"
echo "$SEND/LATEST_RULEBOOK_EXPORT.txt"
echo ""
echo "Quick view:"
echo "less '$SEND/LATEST_RULEBOOK_EXPORT.txt'"
