"""Independent load conditions and retained negative-result integrity."""
import contextlib
import io
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from bus_switching_probe import HERE, cases, duration, measurement, verify


class SwitchingTests(unittest.TestCase):
    def test_published_load_currents_and_transition_limits(self):
        limits = json.loads((HERE/'bus_switching_limits.json').read_text())
        load = limits['switchingLoad']
        self.assertAlmostEqual((load['biasVolts']-.45)/load['resistanceOhms'], .020)
        self.assertAlmostEqual((load['biasVolts']-2.4)/load['resistanceOhms'], -.005)
        values = list(cases())
        self.assertEqual(len(values), 12)
        for case, _, _ in values:
            self.assertEqual(case['withinPublishedLimit'], case['edge'] == 'fall')
        self.assertGreater(min(c['analyticSeconds'] for c,_,_ in values if c['edge']=='rise'), 22e-9)

    def test_closed_form_known_rc_and_unreachable_levels(self):
        load = {'biasVolts':0., 'resistanceOhms':1000., 'capacitanceFarads':1e-9}
        # Parallel equal resistors: 0.5-us time constant, 2-V final level.
        self.assertAlmostEqual(duration(4,1000,load,0,1), .5e-6*math.log(2))
        for start,end in [(0,2),(0,3),(1,0),(1,1)]:
            with self.assertRaises(ValueError): duration(4,1000,load,start,end)
        with self.assertRaises(ValueError): duration(4,-1,load,0,1)
        for log in ('','edge_time = nan','edge_time = -1','edge_time = 1\nedge_time = 1'):
            with self.assertRaises(ValueError): measurement(log)

    def test_retained_evidence_and_corruption(self):
        source = HERE/'reports/bus-switching-candidates'
        with contextlib.redirect_stdout(io.StringIO()): verify(source)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(source,out)
            p=out/'assessment.json';original=p.read_text();r=json.loads(original)
            r['cases'][0]['withinPublishedLimit']=True;p.write_text(json.dumps(r))
            with self.assertRaises(ValueError): verify(out)
            p.write_text(original);r=json.loads(original)
            r['cases'].pop();p.write_text(json.dumps(r))
            with self.assertRaises(ValueError): verify(out)
            p.write_text(original)
            log=out/r['cases'][0]['directory']/'ngspice.log'
            log.write_text(log.read_text().replace('edge_time', 'missing_measurement'))
            with self.assertRaises(ValueError): verify(out)


if __name__ == '__main__': unittest.main()
