import json
from .paths import REG
class Registry:
    def load(self, name): return json.loads((REG / f'{name}.json').read_text())
    def save(self, name, data): (REG / f'{name}.json').write_text(json.dumps(data, indent=2))
    def floors(self): return self.load('floors')
    def lifts(self): return self.load('lifts')
    def workers(self):
        """Canonical: dedupe workers across ALL roster files by worker_id."""
        import re
        seen = set()
        all_workers = []
        for rp in REG.glob('*.json'):
            try: d = json.loads(rp.read_text())
            except: continue
            if not isinstance(d, (dict, list)): continue
            wlist = d.get('workers') if isinstance(d, dict) else (d if isinstance(d, list) else [])
            if not isinstance(wlist, list): continue
            for w in wlist:
                if not isinstance(w, dict): continue
                wid = w.get('worker_id') or w.get('id')
                if not wid or wid in seen: continue
                seen.add(wid)
                all_workers.append(w)
        return all_workers
    def providers(self): return self.load('providers')
    def building(self): return self.load('building')
