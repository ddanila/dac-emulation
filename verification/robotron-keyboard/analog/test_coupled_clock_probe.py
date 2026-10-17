#!/usr/bin/env python3
"""The early probe must preserve board topology and compare identical inputs."""
import copy
import unittest
from coupled_clock_probe import early_deck, matching_inputs


class CoupledClockProbeTests(unittest.TestCase):
    def test_only_transient_window_changes(self):
        deck = 'fixture\nRBR1 a b .001\n.control\ntran 2n 0.127 124m\nwrdata trace.txt v(a)\n.endc\n.end\n'
        self.assertEqual(early_deck(deck, 2, 100), deck.replace('tran 2n 0.127 124m', 'tran 2n 100u'))
        for invalid in (deck.replace('2n', '5n'), deck.replace('124m', '123m'), deck + 'tran 2n 0.127 124m\n'):
            with self.assertRaises(ValueError):
                early_deck(invalid, 2, 100)

    def test_model_and_solver_changes_rejected(self):
        coarse = {key: 'same' for key in ('romSha256', 'connectivitySha256', 'bridge', 'tv80', 'ngspice', 'iverilog', 'sources')}
        coarse.update(assumptions={'maximumStepNs': 2, 'solver': {'reltol': 1e-7}}, hdlSha256={'/coarse/chips.v': 'same'})
        fine = copy.deepcopy(coarse)
        fine['assumptions']['maximumStepNs'] = 1
        fine['hdlSha256'] = {'/fine/chips.v': 'same'}
        matching_inputs(coarse, fine)
        for kind in ('sources', 'solver', 'hdl', 'duplicate'):
            changed = copy.deepcopy(fine)
            if kind == 'sources': changed['sources'] = 'changed'
            if kind == 'solver': changed['assumptions']['solver']['reltol'] = 1e-3
            if kind == 'hdl': changed['hdlSha256']['/fine/chips.v'] = 'changed'
            if kind == 'duplicate': changed['hdlSha256']['/elsewhere/chips.v'] = 'same'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                matching_inputs(coarse, changed)


if __name__ == '__main__':
    unittest.main()
