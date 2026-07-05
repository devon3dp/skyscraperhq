#!/usr/bin/env python3
"""Parallel snapshot_download with max_workers — uses all available bandwidth."""
import argparse, os, time
os.environ.setdefault("HF_HOME", "/vaults/ai/cache/huggingface")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
from huggingface_hub import snapshot_download

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    print(f"[{time.strftime('%H:%M:%S')}] snapshot_download {a.repo} "
          f"workers={a.workers} hf_transfer=on", flush=True)
    t0 = time.time()
    path = snapshot_download(repo_id=a.repo, max_workers=a.workers)
    print(f"[{time.strftime('%H:%M:%S')}] done in "
          f"{round(time.time()-t0)}s → {path}", flush=True)

if __name__ == "__main__":
    main()
