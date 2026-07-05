from .registry import Registry
from .database import init_db
from .lifts import LiftNetwork
class Diagnostics:
    def run(self):
        init_db(); reg=Registry(); out=[]
        def add(n,ok,d=''): out.append({'check':n,'ok':ok,'details':d})
        add('floor_registry', len(reg.floors())==53, str(len(reg.floors())))
        add('lift_registry', len(reg.lifts())>=9, str(len(reg.lifts())))
        add('vacant_floors', len([f for f in reg.floors() if f['vacant']])>=5)
        add('air_llm_cloud', any(p['id']=='air_llm_cloud' for p in reg.providers()))
        add('penthouse_reserved', reg.building()['kernel_installed'] is False)
        try:
            LiftNetwork().send('ground','floor_01','main'); add('lift_delivery', True)
        except Exception as e: add('lift_delivery', False, str(e))
        return {'ok': all(x['ok'] for x in out), 'results': out}
