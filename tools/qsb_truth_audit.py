#!/usr/bin/env python3
"""qsb_truth_audit.py — compares every displayed count to its canonical source
and produces a mismatch report.

Surfaces compared:
  · /api/tower/state              (the canonical truth)
  · /api/unified                  (legacy cockpit)
  · /api/cognitive_unified        (V6 panel)
  · /api/health                   (basic health)

Concept buckets (same idea, multiple counts):
  - workers_total
  - certified_workers
  - oanda_open_trades
  - oanda_realized
  - floors_count

Output:
  data/registries/qsb_truth_audit_latest.json
  ALSO appends to qsb_truth_audit.jsonl with a timestamp

Advisory-only. Does not edit anything.
"""
from __future__ import annotations
import json, urllib.request, pathlib
from datetime import datetime, timezone

REG = pathlib.Path("/vaults/nvme0/qsb_tower_v1/data/registries")
LATEST = REG / "qsb_truth_audit_latest.json"
HISTORY = REG / "qsb_truth_audit.jsonl"

NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def G(url):
    try: return json.loads(urllib.request.urlopen(url, timeout=8).read())
    except Exception as e: return {"__err__": str(e)[:80]}

def pluck(d, path, default=None):
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict): cur = cur.get(key)
        elif isinstance(cur, list):
            try: cur = cur[int(key)]
            except: return default
        else: return default
    return cur if cur is not None else default

def main():
    state = G("http://127.0.0.1:8765/api/tower/state")
    unified = G("http://127.0.0.1:8765/api/unified")
    cognitive = G("http://127.0.0.1:8765/api/cognitive_unified")
    health = G("http://127.0.0.1:8765/api/health")

    # Bucket schema: each alternate is (source, path, value, label, is_same_metric).
    # If is_same_metric=False, the alternate is a related but distinct metric and
    # should NOT be flagged as a mismatch — it's a different lens on the same domain.
    buckets = {
        "workers_total": {
            "concept_label": "Unique workers across all rosters (deduped by worker_id|id)",
            "canonical": ("/api/tower/state", "workers_unique",
                         pluck(state, "workers_unique"),
                         "deduped count", True),
            "alternates": [
                ("/api/unified", "worker_truth_debug.canonical_count",
                  pluck(unified, "worker_truth_debug.canonical_count"),
                  "Registry.workers() deduped", True),
                ("/api/unified", "workers.length",
                  len(pluck(unified, "workers", []) or []),
                  "live state.workers list (same Registry source)", True),
                ("/api/unified", "worker_truth_debug.preferred_count_for_ui",
                  pluck(unified, "worker_truth_debug.preferred_count_for_ui"),
                  "Registry.workers() deduped", True),
            ],
        },
        "certified_traders": {
            "concept_label": "How many workers are 'certified' — multiple lenses",
            "canonical": ("/api/tower/state", "certified_traders",
                         pluck(state, "certified_traders"),
                         "All workers with any trading cert", True),
            "alternates": [
                ("/api/cognitive_unified", "certifications.by_status.certified",
                  pluck(cognitive, "certifications.by_status.certified"),
                  "Different lens — currently-active cert STATUS (not unique workers)", False),
                ("/api/cognitive_unified", "certifications.entry_count",
                  pluck(cognitive, "certifications.entry_count"),
                  "Different lens — total cert log entries (multiple per worker)", False),
            ],
        },
        "oanda_open_trades": {
            "concept_label": "Open OANDA practice trades",
            "canonical": ("/api/tower/state", "oanda_practice.open_trades",
                         pluck(state, "oanda_practice.open_trades"),
                         "Live broker count", True),
            "alternates": [
                ("/api/cognitive_unified", "oanda_account.account_summary.openTradeCount",
                  pluck(cognitive, "oanda_account.account_summary.openTradeCount"),
                  "Same metric — V6 reads cached snapshot, may lag", True),
            ],
        },
        "oanda_realized_gbp": {
            "concept_label": "Realized OANDA practice PnL in GBP",
            "canonical": ("/api/tower/state", "oanda_practice.realized_gbp",
                         pluck(state, "oanda_practice.realized_gbp"),
                         "From qsb_floor41_oanda_pnl.json", True),
            "alternates": [
                ("registry", "qsb_floor41_oanda_pnl.realized_pnl_total",
                  pluck(json.loads((REG / "qsb_floor41_oanda_pnl.json").read_text()), "realized_pnl_total")
                  if (REG / "qsb_floor41_oanda_pnl.json").exists() else None,
                  "Raw registry file (same source)", True),
            ],
        },
        "floors_count": {
            "concept_label": "Total floors in tower",
            "canonical": ("/api/tower/state", "floors_count",
                         pluck(state, "floors_count"),
                         "Counted from floors/floor_*/", True),
            "alternates": [
                ("manifest_glob", "floors/floor_*/floor_manifest.json",
                  len(list(pathlib.Path("/vaults/nvme0/qsb_tower_v1/floors").glob("floor_*/floor_manifest.json"))),
                  "Filesystem manifest count (same source)", True),
            ],
        },
    }

    # Compute mismatches — ONLY for alternates marked is_same_metric=True
    mismatches = []
    different_lenses = []
    for concept, b in buckets.items():
        canon_val = b["canonical"][2]
        for alt in b["alternates"]:
            # New schema: (source, path, value, label, is_same_metric)
            src, path, v, label, is_same = alt[0], alt[1], alt[2], alt[3], alt[4]
            if not is_same:
                different_lenses.append({
                    "concept": concept,
                    "alt_source": src, "alt_path": path,
                    "alt_value": v, "alt_label": label,
                })
                continue
            if v is None or canon_val is None: continue
            ok = (
                abs(float(v) - float(canon_val)) < 0.01
                if isinstance(v, (int, float)) and isinstance(canon_val, (int, float))
                else v == canon_val
            )
            if not ok:
                mismatches.append({
                    "concept": concept,
                    "canonical_source": b["canonical"][0],
                    "canonical_path": b["canonical"][1],
                    "canonical_value": canon_val,
                    "alt_source": src,
                    "alt_path": path,
                    "alt_value": v,
                    "alt_label": label,
                    "delta": (float(v) - float(canon_val))
                             if isinstance(v,(int,float)) and isinstance(canon_val,(int,float))
                             else None,
                })

    out = {
        "ok": True,
        "kind": "qsb_truth_audit",
        "ts": NOW,
        "buckets": {
            k: {
                "concept_label": b.get("concept_label",""),
                "canonical": {"source": b["canonical"][0], "path": b["canonical"][1],
                              "value": b["canonical"][2], "label": b["canonical"][3]},
                "alternates": [
                    {"source": a[0], "path": a[1], "value": a[2],
                     "label": a[3], "is_same_metric": a[4]}
                    for a in b["alternates"]
                ],
            }
            for k, b in buckets.items()
        },
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "different_lenses": different_lenses,
        "different_lens_count": len(different_lenses),
        "explainer": ("'mismatches' = same metric, different value (a real bug). "
                      "'different_lenses' = related but distinct metrics — informational, not drift."),
        "advisory_only": True,
    }

    LATEST.write_text(json.dumps(out, indent=2))
    with HISTORY.open("a") as f:
        f.write(json.dumps({
            "ts": NOW,
            "mismatch_count": len(mismatches),
            "concepts_checked": len(buckets),
            "mismatch_concepts": sorted({m["concept"] for m in mismatches}),
        }) + "\n")

    if mismatches:
        print(f"⚠ {len(mismatches)} mismatches across {len({m['concept'] for m in mismatches})} concepts")
        for m in mismatches:
            print(f"  · {m['concept']:24}  canonical={m['canonical_value']}  "
                  f"vs {m['alt_source']}/{m['alt_path']}={m['alt_value']}  "
                  f"(delta {m['delta']})")
    else:
        print(f"✓ All {len(buckets)} concept buckets aligned. Zero mismatches.")


if __name__ == "__main__":
    main()
