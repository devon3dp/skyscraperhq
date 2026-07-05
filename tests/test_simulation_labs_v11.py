import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.simulation_labs import SimulationLabs

sl = SimulationLabs()
report = sl.run_all()

assert report['floor'] == 'floor_37'
assert report['simulation_only'] is True
assert report['dry_run_only'] is True
assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['execution_enabled'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['model_inference_enabled'] is False
assert report['live_dispatch_enabled'] is False
assert report['writes_real_lift_packets'] is False
assert report['calls_external_providers'] is False
assert report['activates_candidates'] is False
assert report['scenario_count'] >= 5
assert report['passed_scenarios'] == report['scenario_count'], report
assert report['critical_failures'] == 0, report
assert report['warnings'] == 0, report
assert report['packets_simulated'] > 0

dash = sl.dashboard()
assert dash['status'] == 'healthy'
assert dash['worker_execution_enabled'] is False
assert dash['provider_execution_enabled'] is False
assert dash['model_inference_enabled'] is False

print('FLOOR 37 SIMULATION LABS V1.1 VALIDATION PASSED')
print('Status:', report['status'])
print('Scenarios:', report['scenario_count'])
print('Passed:', report['passed_scenarios'])
print('Packets simulated:', report['packets_simulated'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Recommendation:', report['activation_recommendation'])
