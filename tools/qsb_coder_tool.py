#!/usr/bin/env python3
"""
qsb_coder_tool.py — the CODER TOOL that Wren and the CEOs USE (2026-07-18, Ross:
"ceos and wren can use as a tool").

iquest-coder 40B is NOT a worker/CEO of its own. It is a TOOL. When a task needs a real
code deliverable (not a text description), the OWNER CEO (Wren) calls this tool to actually
write the code, then an INDEPENDENT CEO (Pip/Asa) verifies the real output. Governance is
unchanged — this just gives the council a worker capable of producing a genuine deliverable
instead of a qwen text blob that the honest verifier always rejects.

Usage as a library (what the council runner / Wren's agent import):
    from qsb_coder_tool import write_code
    result = write_code(spec="add a Three.js 3D tour to tourguide.html", context=file_text)
    # -> {"ok": True, "code": "...", "model": "iquest-coder-v1:40b-instruct", "elapsed_s": ..}

Usage as a CLI (what a CEO can shell out to):
    python3 tools/qsb_coder_tool.py --spec "..." [--context-file path] [--out path]

No gates flipped. Output is CODE ONLY (returned/written); it does NOT auto-apply to the repo —
applying still goes through the bench multi-sig / council verification. This is a build tool,
not an execution gate.
"""
import os, sys, json, time, argparse, urllib.request

OLLAMA = os.environ.get("QSB_OLLAMA", "http://127.0.0.1:11434") + "/api/generate"
CODER_MODEL = os.environ.get("QSB_CODER_MODEL", "iquest-coder-v1:40b-instruct")

_SYSTEM = (
    "You are the SkyscraperHQ coder tool (iquest-coder 40B). A CEO is USING you to produce a "
    "real, working code deliverable. Output ONLY the code (or unified diff if a target file is "
    "given) — no prose, no markdown fences, no explanation. The code must be complete and runnable, "
    "not a description or placeholder. If a target file's current content is given, produce the FULL "
    "updated file. Never output 'TODO' stubs for the core ask."
)


def write_code(spec: str, context: str = "", target_file: str = "", timeout_s: int = 600,
               model: str = None) -> dict:
    """Call the iquest 40B coder as a tool and return the real code it produces."""
    model = model or CODER_MODEL
    parts = [_SYSTEM, "", f"TASK: {spec}"]
    if target_file:
        parts.append(f"\nTARGET FILE: {target_file}")
    if context:
        parts.append(f"\n--- CURRENT FILE / CONTEXT (produce the full updated version) ---\n{context[:16000]}")
    parts.append("\n--- BEGIN CODE OUTPUT ---")
    prompt = "\n".join(parts)
    # 2026-07-19 FIX C4: scale the output token budget by task complexity — a flat 2048 truncated
    # HTML/3D/dashboard builds mid-file, which verifiers then (correctly) rejected as incomplete.
    _s = (spec + " " + (target_file or "")).lower()
    if any(w in _s for w in ("3d", "webgl", "three.js", "threejs", "dashboard", "game", "shader")):
        _npred = 8192
    elif any(w in _s for w in ("html", "javascript", " js", "css", "page", "widget", "cockpit")):
        _npred = 6144
    else:
        _npred = 3072
    body = {"model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.2, "num_predict": _npred, "num_ctx": 16384}}
    t0 = time.time()
    try:
        req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            j = json.loads(r.read().decode())
        code = (j.get("response") or "").strip()
        # strip accidental markdown fences if the model added them
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
            if code.rstrip().endswith("```"):
                code = code.rstrip()[:-3].rstrip()
        ok = bool(code) and "CANNOT" not in code[:40].upper()
        return {"ok": ok, "code": code, "model": model,
                "elapsed_s": round(time.time() - t0, 1),
                "chars": len(code)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "model": model,
                "elapsed_s": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--context-file", default="")
    ap.add_argument("--target-file", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--model", default=CODER_MODEL)
    a = ap.parse_args()
    ctx = ""
    if a.context_file and os.path.exists(a.context_file):
        ctx = open(a.context_file).read()
    res = write_code(a.spec, context=ctx, target_file=a.target_file, model=a.model)
    if res["ok"] and a.out:
        open(a.out, "w").write(res["code"])
        res["written_to"] = a.out
    # print metadata to stderr, code to stdout (so a CEO can pipe the code)
    print(json.dumps({k: v for k, v in res.items() if k != "code"}), file=sys.stderr)
    if res["ok"]:
        print(res["code"])
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
