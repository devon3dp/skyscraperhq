#!/usr/bin/env python3
"""qsb_hf_download_parallel.py — parallel HF downloader (multiple shards at once).

Default downloader does 1 file at a time. This one runs N workers concurrently.
Combined with HF_HUB_ENABLE_HF_TRANSFER=1 (parallel chunks per file), saturates
the tether faster.

  python3 tools/qsb_hf_download_parallel.py --repo Qwen/Qwen2.5-72B-Instruct --workers 4
"""
import argparse, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault("HF_HOME", "/vaults/ai/cache/huggingface")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

from huggingface_hub import HfApi, hf_hub_download


def fetch(repo, fname):
    t0 = time.time()
    try:
        path = hf_hub_download(repo_id=repo, filename=fname)
        sz = os.path.getsize(path)
        elapsed = time.time() - t0
        rate = sz / max(elapsed, 0.01) / 1e6
        return fname, sz, elapsed, rate, None
    except Exception as e:
        return fname, 0, time.time() - t0, 0, str(e)[:200]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()

    api = HfApi()
    info = api.repo_info(a.repo, files_metadata=True)
    files = [s.rfilename for s in info.siblings]
    total = len(files)
    print(f"[{time.strftime('%H:%M:%S')}] repo={a.repo} files={total} workers={a.workers}", flush=True)

    t_overall = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(fetch, a.repo, f): f for f in files}
        for fut in as_completed(futures):
            fname, sz, elapsed, rate, err = fut.result()
            done += 1
            if err:
                print(f"[{time.strftime('%H:%M:%S')}] {done:2d}/{total} {fname} FAILED: {err}", flush=True)
            else:
                print(f"[{time.strftime('%H:%M:%S')}] {done:2d}/{total} {fname} {sz/1e6:.1f}MB in {elapsed:.0f}s ({rate:.1f} MB/s)", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] all done in {(time.time()-t_overall):.0f}s", flush=True)


if __name__ == "__main__":
    main()
