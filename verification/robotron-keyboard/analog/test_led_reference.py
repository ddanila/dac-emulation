#!/usr/bin/env python3
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from compare_led_reference import intent_events


class LedReferenceTests(unittest.TestCase):
    def events(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'trace.txt'
            p.write_text('time siso caps i_siso i_caps\n' + '\n'.join(rows))
            return intent_events(p)

    def test_bit_mapping_hold_and_transition_band(self):
        result = self.events(['0 5 5 0 0', '.001 0 0 0 0', '.002 2.5 0 0 0',
                              '.003 5 0 0 0', '.004 5 0 0 0', '.005 5 5 0 0',
                              '.006 0 5 0 0', '.007 0 0 0 0'])
        self.assertEqual([v for _, v in result], [0, 1, 3, 2, 0])
        self.assertEqual(result[1][0], .003)

    def test_missing_known_state_is_not_an_empty_pass(self):
        with self.assertRaisesRegex(ValueError, 'No known LED'):
            self.events(['.001 2.5 2.5 0 0', '.002 2.5 2.5 0 0'])

    def test_reversal_and_nonfinite_samples_rejected(self):
        for rows in [['.002 0 0 0 0', '.001 5 5 0 0'], ['.001 nan 0 0 0']]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.events(rows)

    def test_standalone_comparison_rejects_old_pass_with_solver_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            log = path / 'ngspice.log'
            log.write_text('Instance: ahdl Message: XSPICE time is behind vtime:\n')
            report = {'passed': True, 'ledObservation': {'passed': True},
                      'logSha256': hashlib.sha256(log.read_bytes()).hexdigest()}
            (path / 'report.json').write_text(json.dumps(report))
            output = path / 'comparison.json'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('compare_led_reference.py')),
                                     str(path), '--out', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            observed = json.loads(output.read_text())
            self.assertFalse(observed['passed'])
            self.assertIn('Retained solver/HDL diagnostics', observed['error'])


if __name__ == '__main__':
    unittest.main()
