import unittest
from transient_error_control import set_truncation_tolerance


class TransientErrorControlTests(unittest.TestCase):
    def test_preserves_circuit_newton_tolerances_and_requested_steps(self):
        deck='R1 a 0 100\n.options reltol=1e-8 vntol=1e-9 abstol=1e-15\n.control\n.tran 25n 1006000n\n.endc\n'
        for value in (1., .25):
            result=set_truncation_tolerance(deck,value)
            self.assertEqual(result.replace(f'.options trtol={value:.17g}\n',''),deck)

    def test_rejects_relaxation_nonfinite_and_ambiguous_controls(self):
        for value in (0., -1., 2., float('nan'), float('inf')):
            with self.assertRaises(ValueError):set_truncation_tolerance('.control',value)
        for deck in ('', '.control\n.control', '.options trtol=1\n.control', 'set XTRTOL=7\n.control'):
            with self.assertRaises(ValueError):set_truncation_tolerance(deck,.25)


if __name__ == '__main__':
    unittest.main()
