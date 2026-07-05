import sys
sys.path.insert(0, '/vaults/nvme0/qsb_tower_v1/tools')
import asyncio
from qsb_ensemble_coordinator import EnsembleCoordinator

orig = EnsembleCoordinator.on_tick
async def patched(self, event):
    name = event.get('name', '?')
    inst = event.get('payload', {}).get('instrument', '?')
    print(f'[DEBUG] on_tick fired name={name} inst={inst}', flush=True)
    return await orig(self, event)
EnsembleCoordinator.on_tick = patched

c = EnsembleCoordinator('BTCUSDT', 'binance', ['momentum','mean_revert','breakout'], 0.0005)
print('[DEBUG] starting run...', flush=True)
asyncio.run(c.run())
