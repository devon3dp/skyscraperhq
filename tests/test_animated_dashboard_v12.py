import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src' / 'dashboard' / 'server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('animated_dashboard_server', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert 'Animated Skyscraper Cockpit' in mod.HTML
assert 'tower-viewport' in mod.HTML
assert 'lift-car' in mod.HTML
assert '/api/live' in mod.HTML

payload = mod.live_payload()
assert payload['status']['counts']['floors'] == 53
assert payload['status']['counts']['lifts'] >= 9
assert payload['status']['counts']['kernel_installed'] is False
assert 'penthouse' in payload
assert 'monitoring' in payload
assert 'status' in payload

print('ANIMATED DASHBOARD V1.2 VALIDATION PASSED')
print('Floors:', payload['status']['counts']['floors'])
print('Lifts:', payload['status']['counts']['lifts'])
print('Kernel installed:', payload['status']['counts']['kernel_installed'])
