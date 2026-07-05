# Agent Sync Protocol — Federated Council Codebase

Ross 2026-07-02: agents work as a team from any PC. Each agent tails a
shared "what's new" feed and organises the updates their own way.

## The feed

**Path**: `data/registries/qsb_tower_source_diff.jsonl` (grows-only).

**Shape** (one JSON row per file change):

```json
{
  "ts": "2026-07-02T22:21:15Z",
  "node": "24.04ubuntu",
  "path": "tools/qsb_wren_sage.py",
  "sha_before": "abc123def456",
  "sha_after":  "789ghi012jkl",
  "size_before": 4029,
  "size_after":  10435,
  "mtime": 1751495400,
  "author": "ross"
}
```

## The publisher

HQ runs `tools/qsb_source_diff_publisher.py`. On each tick:
1. Scans a whitelist of files in `tools/`.
2. On sha mismatch → appends a row to the feed AND POSTs the file bytes to
   every peer's `/file?name=<relpath>` endpoint.
3. Persists state to `data/registries/qsb_source_diff_state.json`.

Run:
```bash
python3 tools/qsb_source_diff_publisher.py --baseline   # first-time snapshot
python3 tools/qsb_source_diff_publisher.py --once       # one pass
python3 tools/qsb_source_diff_publisher.py              # daemon (30s)
```

## The receiver (per peer)

Node listener at `:9100` accepts `POST /file?name=<relpath>`. It stores the
bytes under `data/team_memory/shared/node_artifacts/<name>`. The peer's
integration script (or Ross) moves it into `tools/` locally — this two-step
handoff means no PC gets its code overwritten silently.

## Agent consumer patterns (each in its own way)

### Sage
Tail the feed. Any change to `qsb_wren_local_agent.py` may invalidate the
current drift thresholds. Sage re-baselines the last 20 sessions after a
Wren update to avoid false-positive drift from the version bump.

### Wren
Tail the feed. On a change to any of her own tools, re-read the tool
definitions on her next session start so her persona knows about new
capabilities.

### Forge
Tail the feed. On a change to `qsb_wren_team.py`, re-resolve the model
fallback list (in case a new model was added).

### TP-Claude (Watcher)
Tail the feed. Any tools/ change is a signal to re-scan the tower shape.
Increment the Watcher's "code-drift" counter, alert if the rate exceeds
2 changes/min (suggests uncontrolled fanning).

### iQuest
Tail the feed. On a change to a file matching a recent iQuest review,
mark that review as stale and re-queue for re-review.

### Ross (dashboard)
The Boardroom Hub timeline reads the feed and shows source-diff rows
inline with Council messages — Ross sees code changes and Council chat
in one place.

## Safety line

- Publisher NEVER pushes files in the SAFETY_DENY list (CLAUDE.md, vault/,
  `.env*`, gate JSONs).
- Publisher does NOT auto-apply on the receiving PC — bytes land in an
  artifact dir. Local Claude/operator moves them into `tools/`.
- Real-money gates remain LOCKED FALSE regardless of any code sync.
- Every push is logged in the feed; auditable across the Council.
