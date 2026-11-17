"""Converter connectivity and early-startup checks; no regulation qualification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab
import reference


class ConverterTests(unittest.TestCase):
    def test_source_connectivity_initialization_and_archive(self):
        profile = ROOT/'profiles/k7222-11-converter.json'
        probes = reference.read_profile(profile)['probes']
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'base'
            report = reference.run(profile, out, stop=.002, step=2e-6)
            rows = reference.read_samples(out/'samples.txt', probes, 0, .002, 2e-6)
            parts = {c['source_id']: c for c in report['components'] if c.get('source_id')}
            self.assertEqual(report['coverage']['connected'], 41)
            self.assertFalse(report['coverage']['full_monitor_qualified'])
            self.assertEqual(parts['012-6931:C8']['value'], '47u')
            self.assertEqual(parts['012-6931:C9']['value'], '3.3n')
            self.assertEqual(parts['012-6931:T1']['nodes'],
                             ['p12_filtered','switch_collector','t1_8','t1_7','0','t1_5'])
            self.assertEqual(parts['012-6931:A1']['nodes'],
                ['p12','converter_ref','converter_fb','converter_gain','converter_ref',
                 'converter_soft','converter_rx','converter_cx','converter_sync','converter_ref',
                 '0','0','0','converter_qe','converter_qc','0'])
            self.assertEqual(report['hashes']['model_parameters_0'], lab.digest((out/'model_parameters_0.json').read_bytes()))
            self.assertTrue((out/'converter_magnetics.py').is_file())
            self.assertGreater(rows[-1][11], 8)
            self.assertLess(max(r[8] for r in rows), 5)
            self.assertGreaterEqual(min(r[5] for r in rows), -.02)
            self.assertLess(rows[-1][6], 1.3)  # Real C8 is still charging.
            self.assertGreater(rows[-1][12], 1)
            refined = Path(tmp)/'refined'
            reference.run(profile, refined, stop=.002, step=1e-6)
            fine = reference.read_samples(refined/'samples.txt', probes, 0, .002, 1e-6)
            for col in (1, 2, 3, 6, 7, 11, 12):
                self.assertAlmostEqual(rows[-1][col], fine[-1][col], delta=max(.001, abs(fine[-1][col])*.01))

    def test_timeout_retains_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); log = out/'timeout.log'
            with self.assertRaises(subprocess.TimeoutExpired):
                lab.run_command([sys.executable, '-c',
                    'import time; print("solver progress", flush=True); time.sleep(10)'], out, log, timeout=.1)
            self.assertIn('solver progress', log.read_text())

    def test_reject_unbounded_or_stale_generated_models(self):
        profile = json.loads((ROOT/'profiles/k7222-11-converter.json').read_text())
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            out = Path(tmp); path = out/'profile.json'
            for generated in ([], {'not-included.cir': 'devices/t1-bound.json'},
                              {'devices/t1-bound.cir': '/tmp/missing.json'},
                              {'devices/t1-bound.cir': 'reference/k7222-11/assembly.json'}):
                profile['generated_models'] = generated
                path.write_text(json.dumps(profile))
                with self.assertRaises(ValueError): reference.read_profile(path)
            stale = out/'stale.cir'; stale.write_text('* stale generated model\n')
            name = str(stale.relative_to(ROOT))
            profile['additional_models'][-1] = name
            profile['generated_models'] = {name: 'devices/t1-bound.json'}
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, 'does not match'): reference.read_profile(path)


if __name__ == '__main__': unittest.main()
