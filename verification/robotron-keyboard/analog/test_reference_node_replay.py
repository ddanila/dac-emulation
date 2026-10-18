#!/usr/bin/env python3
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
                         ['v(out,board_reference)', 'v(host_receiver_5v,0)', 'i(Vhost)'])

    def test_substrate_is_old_global_ground_not_local_emitter(self):
        shifted, _ = transform(FIXTURE, True)
        self.assertIn('.global board_reference\n', shifted)
        self.assertIn('Q1 y a g board_reference NPN_MODEL', shifted)
        self.assertIn('Rlocal g board_reference 1g', shifted)
        control, mapping = transform(FIXTURE, False)
        self.assertNotIn('.global', control)
        self.assertIn('Q1 y a g 0 NPN_MODEL', control)
        self.assertIn('v(out,0)', control)
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


if __name__ == '__main__':
    unittest.main()
