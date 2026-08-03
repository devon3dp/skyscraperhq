---
name: evidence-gated-code-work
description: Enforce evidence-backed repository coding. Use for every Wren task that edits, creates, reviews, tests, or verifies code or dashboards.
---

# Evidence-gated code work

1. Restate the exact target paths and prohibited paths.
2. Read the target bytes and identify one exact unique edit anchor.
3. Record the before SHA-256.
4. Edit only authorized staging paths; never claim an edit from tool intent.
5. Record the after SHA-256 and require it to differ when a change was requested.
6. Run the language static check and the task-specific test.
7. Reread the changed block and verify required markers and forbidden-marker absence.
8. Report FILE_CHANGED, BEFORE_SHA256, AFTER_SHA256, TESTS, RESULT, BLOCKER.

A zero-length tool result is not proof. A model statement is not proof. If any required observation is absent, report BLOCKED, never PASS. Do not run governor, survey, delegation, gene-pool, or unrelated tools during a file-scoped coding task.
