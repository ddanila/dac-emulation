#!/usr/bin/env python3
"""Guard direct electrical wiring and the calibration/qualification boundary."""
import hashlib
import copy
import json
from pathlib import Path
import tarfile
import unittest

from circuit import load
from network_trace import observe_network, PHYSICAL_SIGNALS
from prepare_dynamic_driver import transform, checked_candidate
from ttl7406_dynamic import model
from ttl7406_output_probe import driver_circuit

HERE=Path(__file__).resolve().parent


class DynamicDriverTests(unittest.TestCase):
    def fixture(self):
        components,_=load()
        lines,_=driver_circuit(components,'7406-dc',1000,True,True)
        return '\n'.join(['Direct driver fixture',*lines,
            'Bwr_low n_WR_N 0 I=V(n_WR_N)*V(wr_low)/1000',
            'Bwr_high n_p5V n_WR_N I=(V(n_p5V)-V(n_WR_N))*V(wr_high)/1000',
            'Adrive [dsink csink led1 led0] [data_intent clock_intent led1_v led0_v] drive',
            '.save v(n_D0)', '.save v(n_WR_N)', '.control',
            'wrdata trace.txt v(n_D0) v(n_WR_N)', '.endc', '.end',''])

    def test_direct_path_preserves_passives_and_removes_unknown_dac(self):
        original=self.fixture()
        changed=transform(original,model(.8,.05,.5))
        for line in original.splitlines():
            if line.startswith(('R','C','L','D','Bwr')):
                self.assertIn(line,changed)
        self.assertIn('Xdata n_D0 n_TA_DATEN driver_vp 0 TTL7406_DYNAMIC',changed)
        self.assertIn('Xclock n_WR_N n_TA_TAKT driver_vp 0 TTL7406_DYNAMIC',changed)
        self.assertNotIn('data_intent',changed)
        self.assertNotIn('clock_intent',changed)
        self.assertIn('Adrive [led1 led0] [led1_v led0_v] drive',changed)
        observed=observe_network(changed,PHYSICAL_SIGNALS)
        self.assertIn('i(Vdriver_supply)',observed)
        self.assertEqual([l for l in changed.splitlines() if not l.startswith('.save')],
                         [l for l in observed.splitlines() if not l.startswith(('.save','wrdata network_witness'))])

    def test_digital_input_and_double_counted_capacitance_rejected(self):
        original=self.fixture()
        for bad in (original.replace('Xdata n_D0','Xdata data_intent'),
                    original.replace('Xclock n_WR_N','Xclock clock_intent'),
                    original.replace('Bwr_low n_WR_N','Bwr_low disconnected'),
                    original+'\nCwr_gate n_WR_N 0 3p\n',
                    original+'\nSdata n_TA_DATEN 0 data_intent 0 OUTPUT_SINK_NOMINAL\n'):
            with self.assertRaises(ValueError):
                transform(bad,model(.8,.05,.5))

    def test_retained_device_evidence(self):
        root=HERE/'reports/7406-dynamic'
        report=json.loads((root/'report.json').read_text())
        self.assertTrue(report['completed'])
        self.assertFalse(report['qualified'])
        self.assertFalse(report['boardAdmission'])
        self.assertTrue(report['cases'][0]['selectedScreensPass'])
        self.assertLess(report['cases'][0]['calibration']['objective'],.1)
        self.assertFalse(report['cases'][-1]['selectedScreensPass'])
        checked_candidate(report,0)
        altered=copy.deepcopy(report)
        altered['cases'][0]['parameters']['tf_ns']*=2
        with self.assertRaisesRegex(ValueError,'tested model'):
            checked_candidate(altered,0)
        altered=copy.deepcopy(report)
        altered['cases'][0]['dc'][0]['withinLimit']=False
        with self.assertRaisesRegex(ValueError,'device screens'):
            checked_candidate(altered,0)
        for name,digest in report['sources'].items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),digest,name)
        with tarfile.open(root/'captures.tar.gz') as archive:
            for name,digest in report['artifacts'].items():
                self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(),digest,name)

    def test_withheld_validation_and_settling_interval(self):
        root=HERE/'reports/7406-dynamic/validation'
        report=json.loads((root/'report.json').read_text())
        self.assertTrue(report['completed'])
        self.assertTrue(report['allScreensPass'])
        self.assertFalse(report['qualified'])
        self.assertFalse(report['boardAdmission'])
        self.assertEqual(report['sourceSha256'],hashlib.sha256((HERE/'ttl7406_dynamic_validation.py').read_bytes()).hexdigest())
        self.assertEqual(report['calibrationSha256'],hashlib.sha256((root.parent/'report.json').read_bytes()).hexdigest())
        for case in report['undefinedInput']:
            self.assertGreater(case['holdSeconds'],20*case['loadTimeConstantSeconds'])
            self.assertLess(case['outputDifferenceV'],1e-6)
        with tarfile.open(root/'captures.tar.gz') as archive:
            for name,digest in report['artifacts'].items():
                self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(),digest,name)

    def test_traffic_preflight_preserves_direct_driver(self):
        root=HERE/'reports/7406-dynamic/traffic'
        report=json.loads((root/'assessment.json').read_text())
        self.assertTrue(report['preflightPassed'])
        self.assertFalse(report['qualified'])
        with tarfile.open(root/'captures.tar.gz') as archive:
            for case,entry in report['cases'].items():
                self.assertFalse(entry['electricalExecuted'])
                for name,digest in entry['preparedArtifacts'].items():
                    data=archive.extractfile(f'{case}/{name}').read()
                    self.assertEqual(hashlib.sha256(data).hexdigest(),digest,name)
                    if name=='io.cir':
                        self.assertIn(b'Xdata n_D0 n_TA_DATEN driver_vp 0 TTL7406_DYNAMIC',data)
                        self.assertIn(b'Xclock n_WR_N n_TA_TAKT driver_vp 0 TTL7406_DYNAMIC',data)
                        self.assertNotIn(b'data_intent',data)

    def test_prepared_inputs_and_producer(self):
        root=HERE/'reports/7406-dynamic'
        receipt=json.loads((root/'provenance.json').read_text())
        self.assertTrue(receipt['currentPreparerReproducesAllInputBytes'])
        self.assertEqual(receipt['preparerSha256'],hashlib.sha256((HERE/'prepare_dynamic_driver.py').read_bytes()).hexdigest())
        with tarfile.open(root/'prepared.tar.gz') as archive:
            for name,digest in receipt['preparedInputs'].items():
                self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(),digest,name)


if __name__=='__main__':
    unittest.main()
