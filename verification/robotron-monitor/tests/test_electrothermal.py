from pathlib import Path
import math
import re
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import electrothermal as et
import lab
import lifecycle
import json
from unittest.mock import patch


class ThermalTests(unittest.TestCase):
    def solve(self,directory,step=.05,heater=10.7):
        model=et.model()
        deck=f'''Electrothermal component characterization; not a complete monitor
Vheater hp 0 PWL(0 0 .01 {heater} 200 {heater} 200.01 0)
Vcathode cath 0 PWL(0 0 120 0 120.01 40 140 40 140.01 0)
Vg1 g1 0 -25
Vg2 g2 0 350
Vanode anode 0 11000
Xcrt hp 0 cath g1 g2 anode th tc CRT_THERMAL
{model}
.options reltol=1e-6 abstol=1e-13 method=gear
.control
set wr_singlescale
set wr_vecnames
set numdgt=15
tran {step} 300 0 {step/2}
linearize v(th) v(tc) i(Vheater) i(Vcathode) i(Vg2) i(Vanode)
wrdata samples.txt v(th) v(tc) i(Vheater) i(Vcathode) i(Vg2) i(Vanode)
quit
.endc
.end
'''
        directory.mkdir()
        (directory/'run.cir').write_text(deck)
        log=lab.run_command(['ngspice','-b','run.cir'],directory,directory/'solver.log')
        self.assertIsNone(re.search(r'error|warning|timestep too small|simulation.*aborted',log,re.I),log)
        rows=[list(map(float,line.split())) for line in (directory/'samples.txt').read_text().splitlines()[1:]]
        self.assertAlmostEqual(rows[-1][0],300,places=6)
        self.assertTrue(all(math.isfinite(x) for row in rows for x in row))
        return rows

    def test_warmup_loading_blanking_cooldown_and_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.solve(Path(tmp)/'nominal')
            fine=self.solve(Path(tmp)/'fine',step=.025)
        at=lambda data,t:min(data,key=lambda row:abs(row[0]-t))
        cold,warm,blank,late,cool=[at(rows,t) for t in (1,100,130,190,300)]
        self.assertGreater(warm[2],cold[2]+100)
        self.assertGreater(-warm[6],-cold[6]+1e-9)
        self.assertLess(abs(blank[6]),1e-12)
        self.assertLess(cool[2],late[2])
        self.assertGreater(abs(cold[3]),abs(warm[3]))
        # All electrode currents return to cathode (away from socket transients).
        for t in (1,30,60,100,130,160,190,250,300):
            a,b=at(rows,t),at(fine,t)
            self.assertAlmostEqual(a[4]+a[5]+a[6],0,delta=1e-11)
            for x,y in zip(a[1:],b[1:]):
                self.assertLess(abs(x-y),max(1e-10,.01*abs(y)))
        # Integrate actual heater power minus ambient losses. Internal H->C
        # transfer cancels; stored heat must account for the balance.
        p=et.parameters();ambient=p['ambient_k']
        def net(row):
            t,h,c,ih,*_=row
            vh=10.7*min(t/.01,1) if t<=200 else 10.7*max(0,1-(t-200)/.01)
            losses=p['heater_ambient_g']*h+p['cathode_ambient_g']*c
            losses+=5.670374419e-8*(p['heater_radiation_area']*((h+ambient)**4-ambient**4)
                +p['cathode_radiation_area']*((c+ambient)**4-ambient**4))
            return -vh*ih-losses
        energy=sum((net(a)+net(b))*(b[0]-a[0])/2 for a,b in zip(fine,fine[1:]))
        stored=et.thermal_energy(fine[-1][1],fine[-1][2])
        self.assertAlmostEqual(energy,stored,delta=max(.05,stored*.01))

    def test_bounds_and_unpowered_tube(self):
        for change in [{'work_function_ev':float('nan')},{'perveance':0},{'unknown':1}]:
            with self.assertRaises(ValueError):et.model(change)
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.solve(Path(tmp)/'off',heater=0)
        self.assertLess(max(abs(r[6]) for r in rows),1e-12)
        self.assertLess(max(abs(r[1])+abs(r[2]) for r in rows),1e-6)

    def test_connected_neck_continuous_lifecycle_and_failure_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            nominal=lifecycle.run(root/'nominal')
            refined=lifecycle.run(root/'refined',step=.025)
            self.assertEqual(nominal['status'],'complete')
            self.assertFalse(nominal['full_monitor_qualified'])
            self.assertFalse(nominal['state_reset_at_checkpoints'])
            self.assertEqual(nominal['coverage']['connected'],19)
            self.assertEqual([c['elapsed_s'] for c in nominal['checkpoints']],list(lifecycle.CHECKPOINTS))
            for a,b in zip(nominal['checkpoints'],refined['checkpoints']):
                for name,x in a['values'].items():
                    y=b['values'][name]
                    self.assertLess(abs(x-y),max(1e-10,abs(y)*.01))
            cold,warm=nominal['checkpoints'][0]['values'],nominal['checkpoints'][-1]['values']
            self.assertGreater(warm['cathode_rise'],cold['cathode_rise']+100)
            self.assertGreater(-warm['anode_supply_current'],-cold['anode_supply_current']+1e-9)
            with patch.object(lab,'run_command',side_effect=ValueError('budget exhausted')):
                with self.assertRaises(ValueError):lifecycle.run(root/'failed')
            failed=json.loads((root/'failed/lifecycle.json').read_text())
            self.assertEqual(failed['status'],'incomplete')
            self.assertNotIn('checkpoints',failed)
            self.assertIn('budget exhausted',failed['failure'])


if __name__=='__main__':unittest.main()
