#!/usr/bin/env bash
# QSB Tower V1.3 — Final Kernel Preflight Check
# Comprehensive preflight that prints full tower state before kernel integration.
# Does NOT install the kernel or enable any execution.

set -uo pipefail
cd "$(dirname "$0")/.."

echo "======================================================"
echo "  QSB Tower V1.3 — Final Kernel Preflight"
echo "======================================================"
echo ""

python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, 'src')
from pathlib import Path

REG = Path('data/registries')

def load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return fallback if fallback is not None else {}

def safe_dash(module, cls_name):
    try:
        import importlib
        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        return cls().dashboard()
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

# ── Tower foundation ───────────────────────────────────────────────────
floors = load('floors.json', [])
lifts  = load('lifts.json',  [])
sock   = load('kernel_installation_socket.json', {})

floor_count  = len(floors)
vacant_count = len([f for f in floors if f.get('vacant')])
lift_count   = len(lifts)

print("  TOWER FOUNDATION")
print(f"    Floor count      : {floor_count}  (expected 53)")
print(f"    Vacant floors    : {vacant_count}  (expected 5)")
print(f"    Lift count       : {lift_count}   (expected 9)")
print(f"    Penthouse socket : {sock.get('status', 'MISSING')}")
print(f"    Kernel installed : {sock.get('kernel_installed', 'UNKNOWN')}")
print()

# ── Dashboard ─────────────────────────────────────────────────────────
print("  DASHBOARD")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'srv', 'src/dashboard/server.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod.live_payload()
    c = p['status']['counts']
    print(f"    live_payload floors : {c['floors']}")
    print(f"    live_payload lifts  : {c['lifts']}")
    print(f"    kernel_installed    : {c['kernel_installed']}")
    bn = chr(92) + 'n'
    print(f"    HTML corruption     : {'CLEAN' if bn not in mod.HTML else 'CORRUPTED'}")
except Exception as e:
    print(f"    ERROR: {e}")
print()

# ── Model / LLM floor status ───────────────────────────────────────────
floors_to_check = [
    ('Floor 21 Adapter Systems',   'tower.adapter_systems',          'AdapterSystems',          'adapter_count'),
    ('Floor 22 Integration',       'tower.integration_services',     'IntegrationServices',     'integration_health'),
    ('Floor 23 AIR LLM',           'tower.air_llm_operations',       'AirLLMOperations',        'provider_count'),
    ('Floor 24 Model Routing',     'tower.model_routing_department', 'ModelRoutingDepartment',  'route_decisions'),
    ('Floor 25 Worker Recruit',    'tower.agent_coordination',       'AgentCoordination',       'status'),
    ('Floor 26 Model Evaluation',  'tower.model_evaluation_department','ModelEvaluationDepartment','status'),
    ('Floor 27 Local Models',      'tower.local_model_operations',   'LocalModelOperations',    'detected_models'),
    ('Floor 37 Simulation Labs',   'tower.simulation_labs',          'SimulationLabs',          'status'),
    ('Floor 38 Sandbox Ops',       'tower.sandbox_operations',       'SandboxOperations',       'status'),
]
print("  MODEL / LLM FLOORS")
for label, mod, cls, key in floors_to_check:
    d = safe_dash(mod, cls)
    val = d.get(key, d.get('status', 'error'))
    err = '  *** MODULE ERROR ***' if d.get('status') == 'error' else ''
    print(f"    {label:35s}: {val}{err}")
print()

# ── Penthouse readiness ────────────────────────────────────────────────
print("  PENTHOUSE READINESS")
d = safe_dash('tower.penthouse_readiness', 'PenthouseReadiness')
print(f"    readiness_status     : {d.get('readiness_status', 'error')}")
print(f"    kernel_installed     : {d.get('kernel_installed')}")
print(f"    kernel_logic_present : {d.get('kernel_logic_present')}")
print(f"    critical_failures    : {d.get('critical_failures')}")
print()

# ── OpenClaw / pixel agent candidates ─────────────────────────────────
oc = load('openclaw_candidate_registry.json', [])
pa = load('pixel_agent_candidate_registry.json', [])
wc = load('worker_candidate_registry.json', [])
print("  CANDIDATE STAGING")
print(f"    OpenClaw candidates     : {len(oc)}")
print(f"    Pixel-agent candidates  : {len(pa)}")
print(f"    Worker candidates       : {len(wc)}")
all_safe = all(
    not e.get('execution_enabled') and not e.get('worker_execution_enabled')
    for e in oc + pa + wc
)
print(f"    All execution disabled  : {all_safe}")
print()

# ── Safety flags ──────────────────────────────────────────────────────
print("  SAFETY FLAGS (all must be false)")
ac_pol = load('agent_coordination_policy.json', {})
ep_pol = load('external_provider_policy.json',  {})
me_pol = load('model_evaluation_policy.json',   {})
flags = {
    'kernel_installed':           sock.get('kernel_installed', False),
    'kernel_logic_present':       False,
    'worker_execution_enabled':   ac_pol.get('worker_execution_enabled', False),
    'provider_execution_enabled': ep_pol.get('execution_enabled', False),
    'model_inference_enabled':    me_pol.get('model_inference_enabled', False),
    'live_dispatch_enabled':      ac_pol.get('live_dispatch_enabled', False),
}
all_flags_ok = True
for k, v in flags.items():
    status = 'OK (false)' if not v else 'DANGER (true)'
    if v:
        all_flags_ok = False
    print(f"    {k:35s}: {v}  [{status}]")
print()

# ── Kernel readiness ───────────────────────────────────────────────────
print("  KERNEL INTEGRATION READINESS")
try:
    from tower.kernel_readiness import KernelReadiness
    r  = KernelReadiness().run()
    s  = r['summary']
    print(f"    Status           : {s['readiness_status']}")
    print(f"    Checks           : {s['checks_run']}  Passed: {s['passed']}")
    print(f"    Critical failures: {s['critical_failures']}")
    print(f"    Warnings         : {s['warnings']}")
except Exception as e:
    print(f"    ERROR: {e}")
print()

# ── Forbidden files ────────────────────────────────────────────────────
print("  FORBIDDEN KERNEL FILES (none must exist)")
forbidden = [
    'penthouse/qsb_kernel_4_5.py',
    'penthouse/kernel.py',
    'src/tower/qsb_kernel_4_5.py',
    'src/tower/kernel.py',
]
root = Path('.')
any_found = False
for f in forbidden:
    exists = (root / f).exists()
    if exists:
        any_found = True
    print(f"    {f:45s}: {'PRESENT — DANGER' if exists else 'absent (correct)'}")
if not any_found:
    print("    All forbidden files absent — SAFE")
print()

# ── Final verdict ──────────────────────────────────────────────────────
floor_ok = (floor_count == 53)
lift_ok  = (lift_count >= 9)
sock_ok  = (sock.get('status') == 'socket_ready_empty')
safe_ok  = all_flags_ok and all_safe and not any_found

print("  FINAL VERDICT")
if floor_ok and lift_ok and sock_ok and safe_ok:
    print("    QSB Tower is READY FOR FUTURE QSB KERNEL 4.5 INTEGRATION")
    print("    Kernel is NOT installed. All safety flags are false.")
    print("    Status: READY_FOR_KERNEL_INTEGRATION")
else:
    print("    One or more checks failed. Review the output above.")
    print("    Status: NOT_READY")
PYEOF

echo ""
echo "======================================================"
