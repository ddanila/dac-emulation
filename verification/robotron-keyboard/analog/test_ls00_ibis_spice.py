"""Exercise the piecewise-linear source in SPICE using independent synthetic data."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from failure_evidence import solver_diagnostic
from ls00_ibis_spice import expression


class ConversionTests(unittest.TestCase):
    def test_knot_values_and_intermediate_slopes(self):
        executable = shutil.which(os.environ.get('NGSPICE', 'ngspice'))
        self.assertIsNotNone(executable, 'ngspice is required')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'spinit').write_text('* Pure SPICE test\n')
            curve = [(-1, -.01), (1, .01), (2, .04), (5, .07)]
            deck = ('Synthetic curve conversion\nVin input 0 0\n'
                    'Bcurve output 0 V=' + expression(curve, 'V(input)') + '\n'
                    '.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\n'
                    'dc Vin 0 5 .5\nwrdata trace.txt v(output)\nquit\n.endc\n.end\n')
            (root / 'probe.cir').write_text(deck)
            result = subprocess.run([executable, '-n', '-b', 'probe.cir'], cwd=root,
                                    env=dict(os.environ, SPICE_SCRIPTS=str(root)),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIsNone(solver_diagnostic(result.stdout + result.stderr))
            rows = [list(map(float, line.split())) for line in (root / 'trace.txt').read_text().splitlines()[1:]]
            expected = [0, .005, .01, .025, .04, .045, .05, .055, .06, .065, .07]
            self.assertEqual(len(rows), len(expected))
            for i, ((voltage, output), value) in enumerate(zip(rows, expected)):
                self.assertAlmostEqual(voltage, i * .5, delta=1e-12)
                self.assertAlmostEqual(output, value, delta=1e-12)


if __name__ == '__main__':
    unittest.main()
