import sys
from pathlib import Path
ROOT=Path('/vaults/nvme0/qsb_tower_v1'); sys.path.insert(0,str(ROOT/'src'))
from tower.diagnostics import Diagnostics
d=Diagnostics().run()
print(d)
assert d['ok'] is True
print('VALIDATION PASSED')
