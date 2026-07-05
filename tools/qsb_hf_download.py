#!/usr/bin/env python3
"""qsb_hf_download.py — per-file Hugging Face downloader with live progress.

Lives in the repo (not /tmp) so it survives reboots. Uses hf_transfer for
parallel chunks. Reports per-file rate + total elapsed.

  python3 tools/qsb_hf_download.py --repo Qwen/Qwen2.5-32B-Instruct
"""
import argparse, os, sys, time

os.environ.setdefault("HF_HOME", "/vaults/ai/cache/huggingface")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

from huggingface_hub import HfApi, hf_hub_download

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    a = p.parse_args()

    api = HfApi()
    info = api.repo_info(a.repo, files_metadata=True)
    files = [s.rfilename for s in info.siblings]
    print(f"[{time.strftime('%H:%M:%S')}] repo={a.repo} files={len(files)}", flush=True)

    t_overall = time.time()
    for i, f in enumerate(files, 1):
        t0 = time.time()
        try:
            path = hf_hub_download(repo_id=a.repo, filename=f)
            sz = os.path.getsize(path)
            elapsed = time.time() - t0
            rate = sz / max(elapsed, 0.01) / 1e6
            print(f"[{time.strftime('%H:%M:%S')}] {i:2d}/{len(files)} {f} "
                  f"{sz/1e6:.1f}MB in {elapsed:.0f}s ({rate:.1f} MB/s)",
                  flush=True)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] {i:2d}/{len(files)} {f} "
                  f"FAILED: {str(e)[:200]}", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] all done in "
          f"{round(time.time()-t_overall)}s", flush=True)

if __name__ == "__main__":
    main()
