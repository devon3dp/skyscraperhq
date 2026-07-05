#!/usr/bin/env python3
"""qsb_hf_wget_download.py — bypass the hung HF Python lib with wget -c.

When huggingface_hub.snapshot_download hangs on rate-limited connections,
we lose progress visibility. wget gives real-time progress + supports -c
(resume) so partial files keep going.

Strategy:
  1. Fetch the manifest (tree listing) via the HF REST API
  2. For each file not already complete on disk, wget -c into the
     huggingface cache layout
  3. Log per-file progress + sleep briefly between files (avoid burst
     hammering HF rate limits)

Usage:
  python3 tools/qsb_hf_wget_download.py --repo Qwen/Qwen2.5-32B-Instruct
"""

from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.request, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

CACHE_BASE = Path(os.environ.get("HF_HOME", "/vaults/ai/cache/huggingface")) / "hub"
BIND_ADDRESS: str | None = None  # set by --bind-address CLI flag


def now_hms() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_hms()}] {msg}", flush=True)


def get_tree(repo: str) -> list[dict]:
    """List files in repo via the HF API."""
    url = f"https://huggingface.co/api/models/{repo}/tree/main"
    req = urllib.request.Request(url, headers={"User-Agent": "qsb-hf-wget/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def cache_path(repo: str, filename: str) -> Path:
    """Path where huggingface_hub would cache the file blob.

    HF caches under hub/models--<ns>--<repo>/blobs/<sha>; the snapshot dir
    has symlinks pointing to the blobs. wget can't easily replicate the
    sha-hashed blob path (we don't know sha until we have content), so we
    write directly to snapshots/<commit>/<filename> and let HF's library
    later find them — OR write to a parallel staging directory and move.

    Simplest: write to <repo>/<filename> under a staging dir. Once all
    files exist, we materialise the HF cache layout."""
    repo_dir = repo.replace("/", "--")
    return CACHE_BASE / f"models--{repo_dir}" / "wget_staging" / filename


def download_with_wget(url: str, dest: Path, retries: int = 6,
                        bind_address: str | None = None) -> bool:
    """wget -c with retries. Returns True if file present + complete-ish.

    bind_address: optional source IP to bind to (e.g. Galaxy 172.29.53.207).
    Combined with source-based routing this forces traffic via a
    specific WAN — letting us split a pool across Netgear + Galaxy.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_size = dest.stat().st_size if dest.exists() else 0
    for attempt in range(1, retries + 1):
        log(f"  wget attempt {attempt} (resume from {last_size//1024} KB"
            f"{' bind=' + bind_address if bind_address else ''})")
        cmd = ["wget", "-c", "--tries=1", "--read-timeout=60",
               "--connect-timeout=20",
               "-O", str(dest), url]
        if bind_address:
            cmd[1:1] = [f"--bind-address={bind_address}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        cur_size = dest.stat().st_size if dest.exists() else 0
        gained = cur_size - last_size
        log(f"    rc={r.returncode}  gained {gained//1024} KB  "
            f"total {cur_size//1024} KB")
        if r.returncode == 0:
            return True
        # Backoff for throttling. Increase between retries.
        if gained == 0 and attempt < retries:
            wait = min(30 * attempt, 120)
            log(f"    no progress; sleeping {wait}s before retry")
            time.sleep(wait)
        last_size = cur_size
    return dest.exists() and dest.stat().st_size > 0


def _download_one(repo: str, f: dict, idx: int, total: int,
                   lock: Lock) -> tuple[int, bool, int]:
    """Worker for one file. Returns (idx, ok, final_size)."""
    fname = f["path"]
    size_expected = f.get("size") or 0
    dest = cache_path(repo, fname)
    if (dest.exists() and dest.stat().st_size == size_expected
            and size_expected > 0):
        with lock:
            log(f"{idx:2d}/{total} {fname} already complete "
                f"({size_expected//1024//1024} MB)")
        return idx, True, size_expected
    url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
    with lock:
        log(f"{idx:2d}/{total} {fname} START "
            f"target={size_expected//1024//1024 if size_expected > 1024*1024 else size_expected//1024} "
            f"{'MB' if size_expected > 1024*1024 else 'KB'}")
    ok = download_with_wget(url, dest, bind_address=BIND_ADDRESS)
    cur = dest.stat().st_size if dest.exists() else 0
    with lock:
        if ok and cur == size_expected:
            log(f"{idx:2d}/{total} {fname} ✓ DONE")
        else:
            log(f"{idx:2d}/{total} {fname} partial {cur//1024} KB / "
                f"{size_expected//1024} KB")
    return idx, ok and cur == size_expected, cur


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--sleep-between-files", type=float, default=2.0,
                   help="(sequential mode only)")
    p.add_argument("--parallel", type=int, default=1,
                   help="how many files to download concurrently (default 1)")
    p.add_argument("--bind-address", default=None,
                   help="source IP to bind to (forces a specific WAN with "
                        "source-based routing)")
    p.add_argument("--shard-modulo", type=int, default=1,
                   help="when running multiple pools across WANs, divides the "
                        "file list into this many slices so the pools don't "
                        "race on the same shards (default 1 = take all files)")
    p.add_argument("--shard-offset", type=int, default=0,
                   help="this pool's slice index in [0, shard-modulo). Files "
                        "with idx%modulo==offset belong to this pool. "
                        "Coordinate with sibling pools (e.g. Netgear=0, "
                        "Galaxy=1 when modulo=2).")
    a = p.parse_args()
    global BIND_ADDRESS
    BIND_ADDRESS = a.bind_address

    log(f"manifest fetch: {a.repo}")
    tree = get_tree(a.repo)
    log(f"manifest: {len(tree)} entries")

    files_all = [t for t in tree if t.get("type") == "file"]
    if a.shard_modulo > 1:
        files = [t for i, t in enumerate(files_all)
                 if i % a.shard_modulo == a.shard_offset]
        log(f"shard slice: {len(files)}/{len(files_all)} files "
            f"(modulo={a.shard_modulo} offset={a.shard_offset})")
    else:
        files = files_all
    total_bytes_expected = sum(t.get("size", 0) or 0 for t in files)
    log(f"files: {len(files)}  total bytes expected: "
        f"{total_bytes_expected//1024//1024} MB  parallel={a.parallel}")

    completed = 0
    t0 = time.time()

    if a.parallel > 1:
        # Parallel mode — ThreadPoolExecutor pulls N files at once.
        # Each worker has its own wget process; HF throttles per-connection
        # so more streams = more aggregate bandwidth (within the per-IP cap).
        lock = Lock()
        with ThreadPoolExecutor(max_workers=a.parallel) as ex:
            futures = [
                ex.submit(_download_one, a.repo, f, i, len(files), lock)
                for i, f in enumerate(files, 1)
            ]
            for fut in as_completed(futures):
                try:
                    idx, ok, _ = fut.result()
                    if ok:
                        completed += 1
                except Exception as e:
                    log(f"worker error: {str(e)[:200]}")
    else:
        for i, f in enumerate(files, 1):
            fname = f["path"]
            size_expected = f.get("size") or 0
            dest = cache_path(a.repo, fname)
            if (dest.exists() and dest.stat().st_size == size_expected
                    and size_expected > 0):
                log(f"{i:2d}/{len(files)} {fname} already complete "
                    f"({size_expected//1024//1024} MB)")
                completed += 1
                continue
            url = f"https://huggingface.co/{a.repo}/resolve/main/{fname}"
            log(f"{i:2d}/{len(files)} {fname} target={size_expected//1024} KB")
            ok = download_with_wget(url, dest)
            if ok:
                cur = dest.stat().st_size
                if cur == size_expected:
                    completed += 1
                    log(f"    ✓ complete")
                else:
                    log(f"    partial: {cur//1024} KB / {size_expected//1024} KB")
            else:
                log(f"    ✗ failed after retries")
            time.sleep(a.sleep_between_files)

    elapsed = time.time() - t0
    log(f"done in {elapsed:.0f}s · {completed}/{len(files)} files complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
