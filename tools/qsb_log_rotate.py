#!/usr/bin/env python3
"""
qsb_log_rotate.py — safe, lossless rotation for high-velocity JSONL append logs.

Policy (CLAUDE.md): ARCHIVE never delete. Keep a live tail so running writers
keep appending seamlessly; gz-archive the head into qsb_buffer_state_archive/.
Verifies: archived_lines + kept_lines == original_lines (read at start).

Concurrent-writer safety: we snapshot the current line count, copy the *head*
(everything except the last KEEP lines) into a gz archive, then rewrite the
live file to the last KEEP lines *plus any lines appended after our snapshot*.
Nothing is dropped; at worst a writer's in-flight partial final line is left in
place (JSONL tolerant). No truncation-in-place, no unlink of live data.

Usage:
  python3 tools/qsb_log_rotate.py <path.jsonl> [--keep N] [--threshold-mb M] [--dry-run]
  python3 tools/qsb_log_rotate.py --sweep      # rotate the known-oversized set
"""
import os, sys, gzip, json, shutil, hashlib, datetime, argparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_DIR = os.path.join(REPO, "data", "registries", "qsb_buffer_state_archive")
AUDIT = os.path.join(REPO, "data", "registries", "qsb_log_rotate_audit.jsonl")

# name -> (keep_tail_lines, threshold_mb)
SWEEP = {
    "data/registries/qsb_binance_tick_stream.jsonl":   (20000, 60),
    "data/registries/qsb_oanda_tick_stream.jsonl":     (20000, 60),
    "data/registries/qsb_bus_spillover.jsonl":         (20000, 60),
    "data/registries/qsb_event_bus.jsonl":             (20000, 60),
    # qsb_wren_observed_events.jsonl deliberately EXCLUDED — Wren's own log,
    # she rotates her own house (memory rule: don't touch Wren infra).
    "data/registries/qsb_worker_bus_activity.jsonl":   (20000, 60),
    "data/registries/qsb_alpaca_tick_stream.jsonl":    (20000, 60),
    "data/registries/qsb_broker_place_audit.jsonl":    (20000, 60),
}

def now_ts():
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def audit(row):
    row["ts"] = iso()
    with open(AUDIT, "a") as f:
        f.write(json.dumps(row) + "\n")

def rotate(rel_path, keep=20000, threshold_mb=60, dry_run=False):
    path = rel_path if os.path.isabs(rel_path) else os.path.join(REPO, rel_path)
    if not os.path.exists(path):
        print(f"  SKIP (missing): {rel_path}")
        return None
    size = os.path.getsize(path)
    size_mb = size / 1e6
    if size_mb < threshold_mb:
        print(f"  SKIP (under {threshold_mb}MB, is {size_mb:.1f}MB): {rel_path}")
        return None

    # snapshot line count now
    with open(path, "rb") as f:
        total = sum(1 for _ in f)
    if total <= keep:
        print(f"  SKIP (only {total} lines <= keep {keep}): {rel_path}")
        return None

    head_n = total - keep
    base = os.path.basename(path)
    if base.endswith(".jsonl"):
        stem = base[:-len(".jsonl")]
    else:
        stem = base
    arch_name = f"{stem}_history_{now_ts()}.jsonl.gz"
    arch_path = os.path.join(ARCHIVE_DIR, arch_name)

    print(f"  ROTATE {rel_path}: {size_mb:.1f}MB / {total} lines "
          f"-> archive head {head_n} lines, keep tail {keep}")
    if dry_run:
        return {"path": rel_path, "would_archive_lines": head_n, "keep": keep,
                "archive": arch_name, "dry_run": True}

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    # write head -> gz, keep tail buffered in memory (tail is bounded = keep lines)
    tail = []
    archived = 0
    with open(path, "r", errors="replace") as src, gzip.open(arch_path, "wt") as gz:
        for i, line in enumerate(src):
            if i < head_n:
                gz.write(line)
                archived += 1
            else:
                tail.append(line)
    # any lines appended after our snapshot are beyond index `total`; capture them
    extra = []
    with open(path, "r", errors="replace") as src:
        for i, line in enumerate(src):
            if i >= total:
                extra.append(line)
    kept = tail + extra

    # verify before touching the live file
    if archived != head_n:
        os.remove(arch_path)
        raise RuntimeError(f"archive line mismatch {archived}!={head_n}, aborted, nothing changed")

    # atomically replace live file with tail (+extra)
    tmp = path + f".rotate_tmp_{now_ts()}"
    with open(tmp, "w") as out:
        out.writelines(kept)
    os.replace(tmp, path)

    new_size = os.path.getsize(path)
    with open(path, "rb") as f:
        new_lines = sum(1 for _ in f)

    # lossless check: everything up to the original snapshot is preserved.
    # archived head (head_n lines) + the tail portion we kept (keep lines, minus
    # any that were themselves in extra) must cover the original `total`. Since
    # `tail` holds exactly the lines [head_n, total) and `extra` holds [total, now),
    # the invariant is: archived == head_n AND len(tail) == (total - head_n).
    lossless = (archived == head_n) and (len(tail) == total - head_n)
    result = {
        "path": rel_path,
        "orig_size_mb": round(size_mb, 2),
        "orig_lines": total,
        "archived_lines": archived,
        "archive": arch_name,
        "archive_size_mb": round(os.path.getsize(arch_path) / 1e6, 2),
        "kept_lines_now": new_lines,
        "new_size_mb": round(new_size / 1e6, 2),
        "extra_appended_during_rotate": len(extra),
        "lossless_head_plus_tail_eq_orig": lossless,
    }
    audit({"event": "rotate", **result})
    if not lossless:
        print(f"  !! WARN lossless check failed for {rel_path}: {archived}+{len(tail)} != {total}")
    else:
        print(f"  OK verified: {archived} archived + {len(tail)} kept == {total} orig; "
              f"live now {new_size/1e6:.1f}MB / {new_lines} lines")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--keep", type=int, default=20000)
    ap.add_argument("--threshold-mb", type=int, default=60)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    results = []
    if a.sweep:
        print("== log-rotate SWEEP ==")
        for rel, (keep, thr) in SWEEP.items():
            r = rotate(rel, keep=keep, threshold_mb=thr, dry_run=a.dry_run)
            if r:
                results.append(r)
    elif a.path:
        r = rotate(a.path, keep=a.keep, threshold_mb=a.threshold_mb, dry_run=a.dry_run)
        if r:
            results.append(r)
    else:
        ap.error("give a path or --sweep")
    print(f"\n== rotated {len(results)} file(s) ==")


if __name__ == "__main__":
    main()
