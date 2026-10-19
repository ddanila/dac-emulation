#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


from reference_node_replay import transform


FIXTURE = '''S600 firmware I/O service fixture
Vhost host_receiver_5v host_receiver_gnd PWL(0 0 1u 5)
R1 host_receiver_5v 0 1000
B1 out 0 V=V(host_receiver_5v)*V(out,host_receiver_gnd)/5
.subckt TTL7406_NOMINAL a y vp g params: input_br=1
Q1 y a g NPN_MODEL
Rlocal g 0 1g
.model NPN_MODEL NPN(IS=1e-14 BF=100 BR={input_br})
.ends TTL7406_NOMINAL
X1 out result host_receiver_5v 0 TTL7406_NOMINAL input_br=.01
.save v(out) v(host_receiver_5v,host_receiver_gnd) i(Vhost)
.options reltol=0.0001 vntol=1e-07 abstol=1e-13
.options trtol=1
.tran 50n .001
.control
set numdgt=17
set wr_singlescale
set wr_vecnames
run
wrdata trace.txt v(out) v(host_receiver_5v,host_receiver_gnd)
quit
.endc
.end
'''


class ReferenceNodeTests(unittest.TestCase):
    def test_physical_voltages_and_numeric_values(self):
        deck, mapping = transform(FIXTURE, True)
        self.assertIn('Vhost host_receiver_5v 0 PWL(0 0 1u 5)', deck)
        self.assertIn('R1 host_receiver_5v board_reference 1000', deck)
        self.assertIn('B1 out board_reference V=v(host_receiver_5v,board_reference)*v(out,0)/5', deck)
        self.assertIn('.options reltol=0.0001 vntol=1e-07 abstol=1e-13', deck)
        self.assertIn('.tran 50n .001', deck)
        # Compare transformed observations for arbitrary common-mode potential.
        original = {'0': 0, 'host_receiver_gnd': 2, 'host_receiver_5v': 7, 'out': 3}
        shifted = {'0': 0, 'board_reference': -2, 'host_receiver_5v': 5, 'out': 1}
        self.assertEqual(original['out']-original['0'], shifted['out']-shifted['board_reference'])
        self.assertEqual(original['host_receiver_5v']-original['host_receiver_gnd'],
                         shifted['host_receiver_5v']-shifted['0'])
        self.assertEqual(mapping['observations'][0]['transformed'],
                         ['v(out,board_reference)', 'v(host_receiver_5v)', 'i(Vhost)'])

    def test_substrate_is_old_global_ground_not_local_emitter(self):
        shifted, _ = transform(FIXTURE, True)
        self.assertIn('.global board_reference\n', shifted)
        self.assertIn('Q1 y a g board_reference NPN_MODEL', shifted)
        self.assertIn('Rlocal g board_reference 1g', shifted)
        control, mapping = transform(FIXTURE, False)
        self.assertNotIn('.global', control)
        self.assertIn('Q1 y a g 0 NPN_MODEL', control)
        self.assertIn('v(out)', control)
        self.assertNotIn('v(out,0)', control)
        self.assertEqual(mapping['mappedNodeOccurrences'], 0)

    def test_reject_implicit_or_unreviewed_interfaces(self):
        for line in ['Ahdl [out] model', '.include device.lib', '.ic v(out)=5',
                     'Rbad out 0 R=V(out)', 'Bbad out 0 V=time',
                     'Qextra out out 0 0 NPN_MODEL', '.options gmin=1e-6',
                     'M1 out out 0 0 NMOS']:
            with self.subTest(line=line), self.assertRaises(ValueError):
                transform(FIXTURE.replace('.save', line+'\n.save', 1), True)

    def test_reject_colliding_or_shadowed_nodes(self):
        for deck in [FIXTURE.replace('out', 'board_reference'),
                     FIXTURE.replace('Rlocal g 0', 'Rlocal host_receiver_gnd 0')]:
            with self.assertRaises(ValueError):
                transform(deck, True)


@unittest.skipUnless(os.environ.get('REFERENCE_NODE_NGSPICE'), 'Set REFERENCE_NODE_NGSPICE for solver validation')
class ReferenceNodeSolverTests(unittest.TestCase):
    def test_divider_and_behavioral_voltage_are_reference_invariant(self):
        # Independent DC solution: supply branch is 5 V across 1000 + 100 ohms.
        # The off transistor includes substrate capacitance to exercise its explicit
        # old-ground connection within a subcircuit during the supply rise.
        deck = FIXTURE.replace('R1 host_receiver_5v 0 1000',
                               'R1 host_receiver_5v 0 1000\nRreturn host_receiver_gnd 0 100')
        deck = deck.replace('V=V(host_receiver_5v)*V(out,host_receiver_gnd)/5',
                            'V=V(host_receiver_5v)/2')
        deck = deck.replace('Q1 y a g NPN_MODEL', 'Q1 y g g NPN_MODEL')
        deck = deck.replace('NPN(IS=1e-14 BF=100 BR={input_br})',
                            'NPN(IS=1e-14 BF=100 BR={input_br} CJS=1p)')
        deck = deck.replace('X1 out result host_receiver_5v 0',
                            'X1 out host_receiver_5v host_receiver_5v 0')
        deck = deck.replace('.tran 50n .001', '.tran 50n 5e-6')
        deck = deck.replace('reltol=0.0001 vntol=1e-07 abstol=1e-13',
                            'reltol=1e-8 vntol=1e-12 abstol=1e-16')
        executable = shutil.which(os.environ['REFERENCE_NODE_NGSPICE'])
        self.assertIsNotNone(executable)
        final = []
        with tempfile.TemporaryDirectory() as directory:
            # This analog fixture needs no XSPICE code models or local startup settings.
            (Path(directory)/'spinit').write_text('* isolated analog test\n')
            env = dict(os.environ, SPICE_SCRIPTS=directory)
            for name, text in [('original', deck), ('control', transform(deck, False)[0]),
                               ('shifted', transform(deck, True)[0])]:
                run = Path(directory)/name
                run.mkdir()
                (run/'io.cir').write_text(text)
                process = subprocess.run([executable, '-n', '-b', 'io.cir'],
                                         cwd=run, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(process.returncode, 0, process.stdout+process.stderr)
                self.assertNotIn('Error:', process.stdout+process.stderr)
                rows = [list(map(float, line.split())) for line in
                        (run/'trace.txt').read_text().splitlines()[1:]]
                self.assertAlmostEqual(rows[-1][0], 5e-6, places=14)
                self.assertAlmostEqual(rows[-1][1], 25/11, places=7)
                self.assertAlmostEqual(rows[-1][2], 5, places=7)
                final.append(rows[-1][1:])
        for result in final[1:]:
            for actual, expected in zip(result, final[0]):
                self.assertAlmostEqual(actual, expected, places=9)


if __name__ == '__main__':
    unittest.main()
