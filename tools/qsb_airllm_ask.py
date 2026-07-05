#!/usr/bin/env python3
"""qsb_airllm_ask.py — one-shot call to a big model via AirLLM (F23 lab).

Lets Wren (and the operator) reach a much-larger model than her qwen2.5:7b
brain when she needs deeper reasoning. AirLLM streams layers from disk so
the model can be ~10× her size and still fit the GPU.

Lives in the F23 venv at /vaults/ai/airllm_lab/.venv (separate from
the tower venv — that's where huggingface + airllm + transformers live).

  python3 tools/qsb_airllm_ask.py \\
      --model Qwen/Qwen2.5-32B-Instruct \\
      --prompt "Explain X in 2 sentences"

Hard caps:
  - max-tokens default 256, ceiling 512
  - wall-time default 180s, ceiling 360s
  - model name must be in MODEL_ALLOWLIST
"""

from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LAB_VENV = Path("/vaults/ai/airllm_lab/.venv/bin/python3")
OUT_LOG = ROOT / "data/registries/qsb_airllm_calls.jsonl"

# Allowlist — operator authorises new models by editing this set.
MODEL_ALLOWLIST = {
    "Qwen/Qwen2.5-32B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.1-70B-Instruct",
}


INFERENCE_DRIVER = r"""
import os, sys, json, time
os.environ['HF_HOME'] = '/vaults/ai/cache/huggingface'
os.environ['TRANSFORMERS_CACHE'] = '/vaults/ai/cache/huggingface/transformers'
from airllm import AutoModel
import torch

cfg = json.loads(sys.stdin.read())
model_name = cfg['model']
prompt = cfg['prompt']
max_new = int(cfg.get('max_new_tokens', 256))

t0 = time.time()
m = AutoModel.from_pretrained(model_name, compression='4bit', profiling_mode=False)
load_s = time.time() - t0

inputs = m.tokenizer(prompt, return_tensors='pt', truncation=True, max_length=4096)
inputs = {k: v.to(m.device) for k, v in inputs.items()}

t1 = time.time()
with torch.inference_mode():
    out = m.generate(inputs['input_ids'], max_new_tokens=max_new,
                     do_sample=False, return_dict_in_generate=False,
                     use_cache=True)
gen_s = time.time() - t1
text = m.tokenizer.decode(out[0][inputs['input_ids'].shape[1]:],
                           skip_special_tokens=True)
print(json.dumps({'ok': True, 'reply': text,
                  'load_s': round(load_s, 1),
                  'gen_s': round(gen_s, 1)}))
"""


def now_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def call(model: str, prompt: str, max_new: int = 256,
         timeout: float = 180.0) -> dict:
    if model not in MODEL_ALLOWLIST:
        return {"ok": False, "error": f"model {model!r} not in allowlist"}
    if not LAB_VENV.exists():
        return {"ok": False, "error": "airllm_lab venv missing"}
    cfg = json.dumps({"model": model, "prompt": prompt[:6000],
                       "max_new_tokens": min(max_new, 512)})
    t0 = time.time()
    try:
        r = subprocess.run(
            [str(LAB_VENV), "-c", INFERENCE_DRIVER],
            input=cfg, capture_output=True, text=True,
            timeout=min(timeout, 360))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    wall = round(time.time() - t0, 1)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or "")[-300:], "wall_s": wall}
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        out["wall_s"] = wall
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)[:200],
                "raw": (r.stdout or "")[-300:], "wall_s": wall}


def stamp(row: dict):
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen2.5-32B-Instruct")
    p.add_argument("--prompt", required=True)
    p.add_argument("--max-new", type=int, default=256)
    p.add_argument("--timeout", type=float, default=180.0)
    a = p.parse_args()
    res = call(a.model, a.prompt, a.max_new, a.timeout)
    res["ts"] = now_iso()
    res["model"] = a.model
    res["prompt_head"] = a.prompt[:200]
    stamp(res)
    print(json.dumps(res, indent=2)[:3000])


if __name__ == "__main__":
    main()
