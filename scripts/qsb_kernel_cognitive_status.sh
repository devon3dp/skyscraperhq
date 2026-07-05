#!/usr/bin/env bash
# QSB Kernel — Cognitive Status (read-only)
# Prints the kernel's perception, attention, working memory, self-model,
# reflection, learning assimilation, goal stack, curiosity queue,
# OpenCore supervision, safety locks, and next recommended repair.
#
# Read-only. Never enables execution.

set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$QSB_ROOT"
source scripts/qsb_env.sh 2>/dev/null || true

export PYTHONPATH="${QSB_ROOT}/src:${PYTHONPATH:-}"

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

def L(name):
    p = REG / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def hdr(t):
    print("\n" + t)
    print("=" * len(t))

def kvs(d, keys, indent=2):
    if not isinstance(d, dict):
        print(" " * indent + "(unavailable)")
        return
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            print(" " * indent + f"{k}: {json.dumps(v, default=str)[:240]}")
        else:
            print(" " * indent + f"{k}: {v}")

perception = L("qsb_kernel_perception_snapshot.json")
attention = L("qsb_kernel_attention_state.json")
working = L("qsb_kernel_working_memory.json")
self_model = L("qsb_kernel_self_model.json")
reflection = L("qsb_kernel_reflection_state.json")
learning = L("qsb_kernel_learning_assimilation_state.json")
goals = L("qsb_kernel_goal_stack.json")
curiosity = L("qsb_kernel_curiosity_queue.json")
opencore = L("qsb_kernel_opencore_supervision_state.json")
tick = L("qsb_kernel_cognitive_tick_latest.json")
smoke_v2 = L("qsb_kernel_learning_smoke_test_v2_latest.json")
cog_smoke = L("qsb_kernel_cognitive_smoke_test_latest.json")

print("QSB Kernel — Cognitive Status")
print("=" * 56)
print(f"tick.timestamp_utc:        {tick.get('timestamp_utc') if isinstance(tick, dict) else '(missing)'}")
print(f"learning_smoke_v2:         {(smoke_v2 or {}).get('verdict', '(missing)')}")
print(f"cognitive_smoke_test:      {(cog_smoke or {}).get('verdict', '(missing)')}")

hdr("Perception summary")
if perception:
    print(f"  fresh:   {len(perception.get('fresh_sources') or [])}")
    print(f"  stale:   {len(perception.get('stale_sources') or [])}")
    print(f"  missing: {len(perception.get('missing_sources') or [])}")
    print(f"  confidence: {perception.get('confidence')}")
else:
    print("  (missing — run ./scripts/qsb_kernel_cognitive_tick.sh)")

hdr("Attention priorities")
if attention:
    for it in (attention.get("priority_items") or [])[:10]:
        print(f"  [{it.get('severity'):<8}] #{it.get('priority_rank'):<2} {it.get('issue')}")
        if it.get("recommended_action"):
            print(f"               action: {it.get('recommended_action')}")
else:
    print("  (missing)")

hdr("Working memory")
if working:
    print(f"  mission: {working.get('current_mission')}")
    print(f"  next_recommended_action: {working.get('next_recommended_action')}")
    print(f"  cockpit: {working.get('current_cockpit_target')}")
    sm = working.get("latest_smoke_test_result") or {}
    print(f"  smoke_v2 verdict: {sm.get('verdict')}")
    print(f"  unknowns: {len(working.get('current_unknowns') or [])}")
else:
    print("  (missing)")

hdr("Self-model")
if self_model:
    print(f"  identity: {self_model.get('identity')}")
    print(f"  version: {self_model.get('version')}")
    print(f"  active_local_only: {self_model.get('active_local_only')}")
    print(f"  execution_allowed: {self_model.get('execution_allowed')}")
    mm = self_model.get("missing_cognitive_registries") or []
    if mm:
        print(f"  missing_cognitive_registries: {len(mm)}")
        for r in mm[:6]:
            print(f"    - {r}")
else:
    print("  (missing)")

hdr("Reflection summary")
if reflection:
    print("  current_uncertainties:")
    for u in (reflection.get("current_uncertainties") or [])[:6]:
        print(f"    · {u}")
    print(f"  stale_sources:     {len(reflection.get('stale_sources') or [])}")
    print(f"  missing_registries: {len(reflection.get('missing_registries') or [])}")
    print(f"  failed_tests:      {len(reflection.get('failed_tests') or [])}")
    print("  next_repair_actions:")
    for a in (reflection.get("next_repair_actions") or [])[:6]:
        print(f"    · {a}")
else:
    print("  (missing)")

hdr("Learning assimilation")
if learning:
    print(f"  assimilated_item_count: {learning.get('assimilated_item_count')}")
    for it in (learning.get("assimilated_items") or [])[:5]:
        print(f"    · {it.get('kind')}: {it.get('phase') or it.get('verdict') or it.get('purpose')}")
else:
    print("  (missing)")

hdr("Goal stack")
if goals:
    for g in (goals.get("active_goals") or [])[:10]:
        print(f"  · {g.get('id')}: {g.get('title')}")
else:
    print("  (missing)")

hdr("Curiosity queue")
if curiosity:
    for q in (curiosity.get("queue") or [])[:8]:
        print(f"  · [{q.get('kind')}] {q.get('subject')}: {q.get('question')}")
else:
    print("  (missing)")

hdr("OpenCore / OpenClaw supervision")
if opencore:
    print(f"  openclaw_execution_enabled: {opencore.get('openclaw_execution_enabled')}")
    print(f"  open_tickets: {opencore.get('open_ticket_count')}")
    print(f"  suggested_inspections: {opencore.get('suggested_inspection_count')}")
    for s in (opencore.get("suggested_inspections") or [])[:6]:
        if isinstance(s, dict):
            print(f"    · {s.get('title')}")
else:
    print("  (missing)")

hdr("Safety locks (must all be false)")
sl = (self_model or {}).get("safety_locks") or {}
locks_to_show = [
    "worker_execution_enabled", "provider_execution_enabled",
    "model_inference_enabled", "live_dispatch_enabled",
    "autonomous_workers_enabled", "direct_provider_access",
    "live_trading_enabled", "real_order_execution_enabled",
    "openclaw_execution_enabled", "binance_order_execution_enabled",
    "stock_order_execution_enabled", "web_access_autonomous_enabled",
    "maintenance_auto_repair_enabled",
]
for k in locks_to_show:
    v = sl.get(k)
    print(f"  {k:<38} {v if v is not None else '(unset, treated as false)'}")

hdr("Next recommended repair")
if reflection and reflection.get("next_repair_actions"):
    print("  " + reflection["next_repair_actions"][0])
elif working and working.get("next_recommended_action"):
    print("  " + working["next_recommended_action"])
else:
    print("  ./scripts/qsb_kernel_cognitive_tick.sh")

print("\nadvisory_only=true · execution_allowed=false")
PY
