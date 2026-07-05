import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src/dashboard/server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor37', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()
assert 'simulation_labs' in payload
sl = payload['simulation_labs']

assert sl['floor'] == 'floor_37'
assert sl['simulation_only'] is True
assert sl['dry_run_only'] is True
assert sl['worker_execution_enabled'] is False
assert sl['provider_execution_enabled'] is False
assert sl['model_inference_enabled'] is False
assert sl['writes_real_lift_packets'] is False
assert sl['calls_external_providers'] is False
assert sl['activates_candidates'] is False
assert sl['critical_failures'] == 0
assert 'id="simulationGrid"' in mod.HTML
assert 'Floor 37 Simulation Labs' in mod.HTML

print('DASHBOARD FLOOR 37 V1.1 VALIDATION PASSED')
print('Status:', sl['status'])
print('Scenarios:', sl['scenario_count'])
print('Passed:', sl['passed_scenarios'])
print('Packets simulated:', sl['packets_simulated'])
print('Dry run:', sl['dry_run_only'])
