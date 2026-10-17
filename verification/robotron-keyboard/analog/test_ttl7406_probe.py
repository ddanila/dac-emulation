#!/usr/bin/env python3
"""A logical inverter must not pass the electrical gate with excessive input current."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TTL7406ProbeTests(unittest.TestCase):
    def test_generic_rejected_and_explicit_dc_candidate_stays_unqualified(self):
        with tempfile.TemporaryDirectory() as temporary:
            for beta, expected_success in [(1, False), (.01, True)]:
                out = Path(temporary) / str(beta)
                proc = subprocess.run([
                    sys.executable, str(Path(__file__).with_name('ttl7406_probe.py')),
                    '--ngspice', os.environ.get('NGSPICE', 'ngspice'),
                    '--input-reverse-beta', str(beta), '--require-dc-points', '--out', str(out),
                ], capture_output=True, text=True, timeout=60)
                report = json.loads((out / 'report.json').read_text())
                self.assertTrue(report['completed'], proc.stderr)
                self.assertFalse(report['qualified'])
                self.assertEqual(proc.returncode == 0, expected_success, proc.stderr)
                self.assertEqual(report['dcPointsWithinPublishedLimits'], expected_success)
                if not expected_success:
                    self.assertFalse(report['cases']['input-high']['withinLimit'])
                    self.assertIn('misses selected DC limits', report['error'])


if __name__ == '__main__':
    unittest.main()
