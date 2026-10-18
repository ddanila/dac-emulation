"""Retained evidence remains a failure even when serial transport agrees."""
import hashlib
import json
import lzma
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ReviewTests(unittest.TestCase):
    def fixture(self, root):
        root.mkdir()
        (root / 'rom.bin').write_bytes(bytes(2048))
        (root / 'scenario.json').write_text(json.dumps({'cycles': 30000}))
        (root / 'reference.log').write_text('BIT 100 1\n')
        (root / 'ngspice.log').write_text(
            'BUS_SAMPLE 1000000 0000 XX 1 0 1\nBUS_LATCH 1001000 XX XX\n'
            'BUS_DRIVE 1000000 000000000000000000000000 000000000000000000000000\n'
            'SERIAL_TX 2000000 1\nSERIAL_RX 2001000 1\n')
        with lzma.open(root / 'bus-trace.txt.xz', 'wt') as f:
            f.write('time ' + ' '.join(f'v(n_D{i})' for i in range(8)) + ' v(n_p5V)\n')
            for time in (0, .000001, .03):
                f.write(str(time) + ' 1.5 0 0 0 0 0 0 0 5\n')
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        report = {'passed': False, 'error': 'Original bus failure', 'assumptions': {'stepNs': 5},
                  'romSha256': sha(root / 'rom.bin'), 'scenarioSha256': sha(root / 'scenario.json'),
                  'referenceLogSha256': sha(root / 'reference.log'),
                  'failureArtifacts': {name: {'sha256': sha(root / name)}
                                       for name in ('ngspice.log', 'bus-trace.txt.xz')}}
        (root / 'report.json').write_text(json.dumps(report))

    def run_review(self, root, out):
        return subprocess.run([sys.executable, str(HERE / 'review_firmware_run.py'),
                               '--run', str(root), '--rom', str(root / 'rom.bin'),
                               '--out', str(out)], capture_output=True, text=True)

    def test_independent_serial_pass_does_not_qualify_unknown_bus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'input', Path(tmp) / 'review'
            self.fixture(root)
            original = (root / 'report.json').read_bytes()
            run = self.run_review(root, out)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads((out / 'assessment.json').read_text())
            self.assertFalse(result['qualified'])
            self.assertFalse(result['originalPassed'])
            self.assertTrue(result['serialBitsMatchC'])
            self.assertEqual(result['recheckedBusFailure']['signal'], 'CPU_DI_UNKNOWN')
            self.assertTrue((out / 'first-read-window.txt').exists())
            self.assertEqual((root / 'report.json').read_bytes(), original)

    def test_final_missing_latch_does_not_hide_earlier_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'input', Path(tmp) / 'review'
            self.fixture(root)
            with (root / 'ngspice.log').open('a') as f:
                f.write('BUS_SAMPLE 3000000 0001 00 0 1 1\n'
                        'BUS_DRIVE 3000000 000000000000000000000000 000000000000000000000000\n')
            report = json.loads((root / 'report.json').read_text())
            report['failureArtifacts']['ngspice.log']['sha256'] = hashlib.sha256(
                (root / 'ngspice.log').read_bytes()).hexdigest()
            (root / 'report.json').write_text(json.dumps(report))
            run = self.run_review(root, out)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads((out / 'assessment.json').read_text())
            self.assertEqual(result['recheckedError'], 'Missing bus samples or CPU latch confirmations')
            self.assertEqual(result['confirmedPrefix']['busFailure']['signal'], 'CPU_DI_UNKNOWN')
            self.assertFalse(result['qualified'])
            self.assertFalse(result['confirmedPrefix']['qualified'])

    def test_modified_capture_is_rejected_before_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'input', Path(tmp) / 'review'
            self.fixture(root)
            with (root / 'bus-trace.txt.xz').open('ab') as f:
                f.write(b'changed')
            run = self.run_review(root, out)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Artifact hash differs', run.stderr)
            self.assertFalse((out / 'assessment.json').exists())


if __name__ == '__main__':
    unittest.main()
