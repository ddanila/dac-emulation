#!/usr/bin/env python3
"""Check observation integrity and keep unvalidated recovery out of admission."""
import hashlib
import json
import lzma
from pathlib import Path
import tarfile
import tempfile
import unittest

from network_trace import PHYSICAL_SIGNALS
from serial_device_trace import observe, SIGNALS
from serial_device_review import samples
from serial_path_admission import assess

HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/serial-path'


class SerialPathTests(unittest.TestCase):
    def test_internal_probes_do_not_change_live_elements(self):
        source=(HERE/'reports/7406-dynamic/live/25/io.cir').read_text()
        changed=observe(source)
        def elements(deck):
            return [line for line in deck.splitlines() if not line.startswith(('.save ','wrdata serial_device.txt'))]
        self.assertEqual(elements(source),elements(changed))
        self.assertTrue(all(s in changed for s in SIGNALS))
        for bad in (source.replace('Xdata n_D0','Bad n_D0'),
                    source.replace('.save ','.discard '),
                    source.replace('wrdata witness.txt','wrdata unknown.txt')):
            with self.assertRaises(ValueError):observe(bad)

    def test_trace_rejects_missing_nonfinite_and_reordered_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.txt'
            for body in ('0 1\n1 nan\n','0 1\n0 2\n','0 1 2\n','1 1\n0 2\n'):
                path.write_text('time v(a)\n'+body)
                with self.assertRaises(ValueError):list(samples(path,['v(a)']))

    def test_retained_replay_controls_and_failure_are_explicit(self):
        root=ROOT/'recovery';report=json.loads((root/'report.json').read_text())
        self.assertTrue(report['completed'])
        self.assertFalse(report['qualified'])
        self.assertFalse(report['boardAdmission'])
        for name,digest in report['sources'].items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),digest,name)
        retained=json.loads((root/'retention.json').read_text())
        self.assertEqual(retained['sourceSha256'],hashlib.sha256((HERE/'retain_serial_recovery.py').read_bytes()).hexdigest())
        with tarfile.open(root/'captures.tar.gz') as archive:
            for name,digest in report['artifacts'].items():
                data=archive.extractfile(name).read();entry=retained['artifacts'][name]
                self.assertEqual(entry['originalSha256'],digest,name)
                self.assertEqual(hashlib.sha256(data).hexdigest(),entry['retainedSha256'],name)
                if 'selection' in entry:
                    rows=[list(map(float,line.split())) for line in lzma.decompress(data).splitlines()[1:]]
                    case=report['runs'][name.split('/')[0]]
                    self.assertAlmostEqual(min(r[2] for r in rows),case['minimumOutputV'],places=12)
                    self.assertEqual(len(rows),entry['rows'])
        comparison=json.loads((root/'assessment.json').read_text())
        self.assertEqual(comparison['sourceSha256'],hashlib.sha256((HERE/'serial_recovery_review.py').read_bytes()).hexdigest())
        self.assertGreater(comparison['sameStepDeviceSensitivity']['maximumDifferenceV'],1)
        self.assertTrue(all(r['maximumDifferenceV']<.001 for r in comparison['refinement']))
        runs=report['runs']
        for name in ('control','long-prelude','half-step','quarter-step','load-15pf','load-100pf','fixed-ground','small-inductance'):
            self.assertTrue(runs[name]['completed'],name)
        self.assertGreater(runs['control']['peakDifferenceFromLiveOutputV'],.1)
        for name in ('long-prelude','half-step','quarter-step'):
            self.assertLess(runs[name]['peakDifferenceFromLiveOutputV'],.003)
            self.assertLess(runs[name]['minimumOutputV'],-1.9)
        self.assertGreater(runs['load-15pf']['minimumOutputV'],runs['quarter-step']['minimumOutputV']+1)
        self.assertFalse(runs['extended-prelude']['completed'])
        self.assertIn('Timestep too small',runs['extended-prelude']['error'])
        self.assertFalse(report['allRunsCompleted'])

    def test_full_board_observation_preserves_control_and_checks_current_balance(self):
        root=ROOT/'internal';report=json.loads((root/'assessment.json').read_text())
        self.assertTrue(report['completed'])
        self.assertTrue(report['networkByteIdenticalToControl'])
        self.assertTrue(report['firmwareMatchesControl'])
        self.assertFalse(report['boardAdmission'])
        self.assertEqual(report['sourceSha256'],hashlib.sha256((HERE/'serial_device_review.py').read_bytes()).hexdigest())
        self.assertEqual(report['observerSha256'],hashlib.sha256((HERE/'serial_device_trace.py').read_bytes()).hexdigest())
        self.assertLess(report['maximumOutputKclResidualA'],1e-6)
        self.assertGreater(report['maximumBaseKclResidualA'],1e-6)
        self.assertTrue(report['currentBalanceScreen']['outputPassed'])
        self.assertFalse(report['currentBalanceScreen']['basePassed'])
        event=report['atMinimum']
        self.assertLess(event['network']['v(n_TA_DATEN)'],-1.9)
        self.assertGreater(event['device']['@q.xdata.qoutput[vbc]'],.6)
        self.assertLess(event['device']['@q.xdata.qoutput[ic]'],0)
        self.assertTrue(report['dataCollectorExceedsPublishedSinkTestCurrent'])
        baseline=json.loads((HERE/'reports/7406-dynamic/live/25/retention.json').read_text())
        self.assertEqual(report['artifacts']['network_witness.txt'],baseline['retainedRawSha256']['network_witness.txt'])
        for name in ('io.cir','run.json'):
            self.assertEqual(report['artifacts'][name],hashlib.sha256((root/name).read_bytes()).hexdigest())
        retention=json.loads((root/'retention.json').read_text())
        for name,record in retention['compressed'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),record['sha256'],name)
            self.assertEqual(report['artifacts'][record['originalName']],record['originalSha256'],name)

    def test_numerical_success_does_not_open_physical_traffic_gate(self):
        report=assess(ROOT)
        self.assertEqual(report,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(report['unchangedLiveControl'])
        self.assertTrue(report['inputLevelsPassSampledCpuCases'])
        self.assertTrue(report['supplyAnchoredEndpointHypothesisPasses'])
        self.assertFalse(report['boardAdmission'])
        self.assertFalse(report['representativeTraffic']['electricalExecuted'])
        self.assertFalse(report['representativeTraffic']['admissionPassed'])
        self.assertTrue(report['physicalEvidenceGaps'])
        self.assertEqual(set(report['evidenceTiers']),{'published','bench','specimen'})
        self.assertFalse(report['evidenceTiers']['specimen']['blocksFunctionalReference'])


if __name__=='__main__':unittest.main()
