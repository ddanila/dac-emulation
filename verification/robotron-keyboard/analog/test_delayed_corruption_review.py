from pathlib import Path
import tempfile
import unittest
from delayed_corruption_review import fault


class FaultReviewTests(unittest.TestCase):
    def test_requires_delayed_fault_after_prior_execution_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            valid = ('H_REJECT 0.000001 equal=1\nFIRST_FETCH 2000000 0000 af\n'
                     'HISTORY_CORRUPTION time=0.000011 after=0.00001\n'
                     'E_CORRUPT output-delay\nH_REJECT 0.000011 equal=0\n'
                     'Rejected trial changed XSPICE history\n')
            path.write_text(valid)
            r = fault(path, .00001)
            self.assertTrue(r['priorFirstFetch'])
            self.assertEqual(r['earlierUnchangedRejections'], 1)
            variants = [valid.replace('time=0.000011', 'time=0.000009'),
                        valid.replace('after=0.00001', 'after=0'),
                        valid.replace('time=0.000011', 'time=nan'),
                        valid.replace('FIRST_FETCH', 'NO_FETCH'),
                        valid.replace('H_REJECT 0.000001 equal=1\n', ''),
                        valid.replace('equal=0', 'equal=1'),
                        valid + 'E_CORRUPT output-delay\n',
                        valid + 'H_REJECT 0.000012 equal=1\n']
            for i, text in enumerate(variants):
                with self.subTest(case=i):
                    path.write_text(text)
                    with self.assertRaises(ValueError): fault(path, .00001)

    def test_immediate_control_needs_no_prior_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            path.write_text('HISTORY_CORRUPTION time=0.0000005 after=0\nE_CORRUPT output-delay\n'
                            'H_REJECT 0.0000005 equal=0\nRejected trial changed XSPICE history\n')
            self.assertFalse(fault(path, 0)['priorFirstFetch'])


if __name__ == '__main__': unittest.main()
