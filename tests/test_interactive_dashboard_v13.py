import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src' / 'dashboard' / 'server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('interactive_dashboard_server', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

required = [
    'Interactive Command Center',
    'selectFloor',
    'selectLift',
    'p-trail',
    'zone-btn',
    'Vacant-Floor Activation Preview',
    'LIVE ACTIVITY FEED',
    'penthouseBanner',
    'towerRows'
]

for item in required:
    assert item in mod.HTML, f'Missing dashboard feature: {item}'

payload = mod.live_payload()
assert payload['status']['counts']['floors'] == 53
assert payload['status']['counts']['lifts'] >= 9
assert payload['status']['counts']['kernel_installed'] is False
assert 'activity' in payload
assert 'penthouse' in payload
assert 'expansion' in payload

print('INTERACTIVE DASHBOARD V1.3 VALIDATION PASSED')
print('Floors:', payload['status']['counts']['floors'])
print('Lifts:', payload['status']['counts']['lifts'])
print('Kernel installed:', payload['status']['counts']['kernel_installed'])
print('Activity records:', len(payload['activity']))
