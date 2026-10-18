"""Check independent current bookkeeping and the retained branch diagnostic."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from ls00_branch_probe import topology, signals_for, balances

HERE = Path(__file__).resolve().parent


class BranchTests(unittest.TestCase):
    def test_device_polarities_and_missing_current(self):
        elements = [('r', 'r.load', ['vp', 'y'], 1000),
                    ('d', 'd.clamp', ['0', 'y'], None),
                    ('q', 'q.sink', ['y', 'a', '0'], None)]
        values = {'v(vp)': 5, 'v(y)': 1, '@d.clamp[id]': .001,
                  '@q.sink[ic]': .005, '@q.sink[ib]': .0001, '@q.sink[ie]': -.0051}
        self.assertTrue(balances(elements, values)['y']['balanced'])
        values['@d.clamp[id]'] = 0
        self.assertFalse(balances(elements, values)['y']['balanced'])
        values['@d.clamp[id]'] = -.001
        self.assertFalse(balances(elements, values)['y']['balanced'])

    def test_nested_ports_and_unsupported_element(self):
        model = '''.subckt LS00_TRANSISTOR_CANDIDATE a b y vp g
Xinner y g child
.ends
.subckt child c e
Qone c c e npn
Rload c e 2k
.ends
.model npn NPN(BF=100)
'''
        elements = topology(model)
        self.assertEqual(elements[0][2], ['y', 'y', '0'])
        self.assertIn('@q.xgate.xinner.qone[ie]', signals_for(elements))
        with self.assertRaisesRegex(ValueError, 'Unsupported circuit element'):
            topology(model.replace('Rload c e 2k', 'Cload c e 2p'))

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice unavailable')
    def test_branches_survive_reduced_numerical_conductance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / 'model.cir'
            source = (HERE / 'ls00_transistor_candidate.cir').read_text()
            self.assertIn('D(IS=1e-8 ', source)
            model.write_text(source.replace('D(IS=1e-8 ', 'D(IS=1e-12 '))
            out = root / 'run'
            subprocess.run([sys.executable, str(HERE / 'ls00_branch_probe.py'),
                            '--model', str(model), '--out', str(out), '--gmin', '1e-15'],
                           check=True, capture_output=True, text=True, timeout=60)
            report = json.loads((out / 'assessment.json').read_text())
            self.assertTrue(report['completed'])
            self.assertTrue(report['nodeKclPassed'])
            self.assertFalse(report['qualified'])
            self.assertGreater(abs(report['branches'][0]['outputVolts'] -
                                   report['branches'][1]['outputVolts']), .5)
            for branch in report['branches']:
                self.assertIn('xgate.collector', branch['nodes'])
                self.assertIn('y', branch['nodes'])


if __name__ == '__main__':
    unittest.main()
