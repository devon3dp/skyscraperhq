#!/usr/bin/env python3
"""
qsb_wren_consult_gene_pool.py — Wren's governed gene-pool consultation tool (Wren Governor Upgrade §8).
Wren (or her agent) calls consult_gene_pool() to get a specialist answer from the Pi Brain Router gene
pool: one governed non-Claude model, free-only, provider/model recorded. Wren remains the decision maker
— the gene-pool model is an adviser. If the Pi is unreachable, returns available=False so Wren falls back
to her local model (never Claude automatically).

Endpoint + token come from the HQ vault (.env.gene_pool, 0600) — never hard-coded, never printed.
CLI:  python3 tools/qsb_wren_consult_gene_pool.py "your question" [task_class]
"""
import os, sys, json, urllib.request

ROOT = os.environ.get("QSB_ROOT", "/vaults/nvme0/qsb_tower_v1")
VAULT = os.path.join(ROOT, "floors", "floor_28_security_department", "vault", ".env.gene_pool")


def _vault():
    d = {}
    try:
        for line in open(VAULT, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); d[k.strip()] = v.strip()
    except Exception:
        pass
    return d


def consult_gene_pool(question, task_class="general", producer_family=None, redacted_context="",
                      timeout=45, max_tokens=None):
    """Ask the Pi gene pool one governed specialist. Returns dict:
    {available, ok, answer, hosting_provider, model, latency_ms} or {available:False} if Pi unreachable."""
    v = _vault()
    tok = v.get("SKY_SERVICE_TOKEN")
    urls = [v.get("GENE_POOL_URL"), v.get("GENE_POOL_URL_WIFI")]  # cable first, WiFi fallback
    if not (tok and any(urls)):
        return {"available": False, "reason": "gene pool endpoint/token not configured"}
    # 2026-07-22: the router's default 700-token cap TRUNCATES code deliverables mid-file (council
    # verifiers correctly rejected "cuts off mid-style-block"). Give code/reasoning tasks real headroom
    # so the producer can return a complete artifact; short chats stay small.
    if max_tokens is None:
        # code/reasoning need room for a COMPLETE artifact AND, on correction attempts, the re-injected
        # prior artifact's full rebuild (~11-12k-char HTML pages). 8000 tokens keeps them from truncating.
        max_tokens = 8000 if task_class in ("coding", "reasoning", "independent_verification") else 900
    body = json.dumps({"task_class": task_class, "question": question,
                       "producer_family": producer_family, "redacted_context": redacted_context[:8000],
                       "free_only": True, "paid_allowed": False, "max_tokens": int(max_tokens)}).encode()
    for base in [u for u in urls if u]:
        try:
            req = urllib.request.Request(base + "/gene_pool/consult", data=body,
                                         headers={"Content-Type": "application/json", "X-Service-Token": tok},
                                         method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read() or b"{}")
            return {"available": True, **d}
        except Exception:
            continue
    return {"available": False, "reason": "Pi gene pool unreachable (Wren falls back to local model)"}


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Say OK in one word."
    tc = sys.argv[2] if len(sys.argv) > 2 else "general"
    r = consult_gene_pool(q, tc)
    print(json.dumps({k: (v[:200] if isinstance(v, str) else v) for k, v in r.items()}, indent=2))
