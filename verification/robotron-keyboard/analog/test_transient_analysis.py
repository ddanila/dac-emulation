#!/usr/bin/env python3
"""Breakpoint selection must preserve the full boot window and all circuit lines."""
import unittest
from transient_analysis import with_minimum_breakpoint


class TransientAnalysisTests(unittest.TestCase):
    deck = ('fixture\nRBR2 a b .001\n.options reltol=.001\n.control\n'
            'set wr_vecnames\ntran 2n 0.127 124m\nwrdata trace.txt v(a)\n.endc\n.end\n')

    def test_default_and_explicit_invocation(self):
        self.assertEqual(with_minimum_breakpoint(self.deck, None), self.deck)
        expected = self.deck.replace('.control\n', '.options minbreak=1f\n.tran 2n 0.127 124m\n.control\n')
        expected = expected.replace('\ntran 2n 0.127 124m\n', '\nrun\n')
        self.assertEqual(with_minimum_breakpoint(self.deck, 1), expected)

    def test_invalid_or_conflicting_analysis_rejected(self):
        for invalid in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                with_minimum_breakpoint(self.deck, invalid)
        for extra in ('.tran 1n 1u\n', '.OPTIONS minbreak=2f\n', 'run\n',
                      'tran 1n 1u\n', '.control\n.endc\n'):
            with self.assertRaises(ValueError):
                with_minimum_breakpoint(self.deck.replace('.control\n', extra + '.control\n'), 1)
        with self.assertRaises(ValueError):
            with_minimum_breakpoint(self.deck.replace('tran 2n 0.127 124m\n', ''), 1)


if __name__ == '__main__':
    unittest.main()
