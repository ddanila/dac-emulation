#!/usr/bin/env python3
"""Keep a passing drive screen distinct from an admitted physical CPU model."""
import hashlib
import json
import math
from pathlib import Path
import tarfile
import unittest

from cpu_serial_drive import endpoint, high_resistance, first_crossing

HERE=Path(__file__).resolve().parent


class CpuSerialDriveTests(unittest.TestCase):
    def test_nominal_control_fails_low_supply_but_anchored_hypothesis_does_not(self):
        profile=json.loads((HERE/'bus_limits.json').read_text())['profiles']['U880']
        self.assertFalse(endpoint(4.75,profile,False)['passed'])
        self.assertAlmostEqual(endpoint(4.75,profile,False)['loadedHighV'],2.15)
        for supply in (4.75,5,5.25):
            self.assertTrue(endpoint(supply,profile,True)['passed'])
            self.assertAlmostEqual(endpoint(supply,profile,True)['loadedHighV'],2.4)
        for supply in (4.5,5.5,math.nan,math.inf):
            with self.assertRaises(ValueError):high_resistance(supply,profile,True)

    def test_missing_and_wrong_direction_transitions_are_rejected(self):
        rows=[[0,0],[1,.5],[2,2],[3,3]]
        self.assertEqual(first_crossing(rows,1,2,True,0,3),[1,2])
        for direction,begin,end in ((False,0,3),(True,2,3),(True,0,1)):
            with self.assertRaises(ValueError):first_crossing(rows,1,2,direction,begin,end)

    def test_reproducible_evidence_does_not_promote_endpoint_fit(self):
        root=HERE/'reports/serial-path/cpu-drive'
        report=json.loads((root/'report.json').read_text())
        self.assertTrue(report['completed'])
        self.assertFalse(report['qualified'])
        self.assertFalse(report['boardAdmission'])
        self.assertTrue(all(r['levelsPass'] for r in report['runs']))
        self.assertEqual({r['temperatureC'] for r in report['runs']},{0,25,70})
        self.assertEqual({r['supplyV'] for r in report['runs']},{4.75,5,5.25})
        self.assertEqual({r['pinPf'] for r in report['runs']},{10,34})
        self.assertEqual({r['anchored'] for r in report['runs']},{False,True})
        for name,digest in report['sources'].items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),digest,name)
        with tarfile.open(root/'captures.tar.gz') as tar:
            for name,digest in report['artifacts'].items():
                self.assertEqual(hashlib.sha256(tar.extractfile(name).read()).hexdigest(),digest,name)
        runs=report['limitingCaseRefinement']
        for a,b in zip(runs,runs[1:]):
            self.assertEqual(a['stepNs'],2*b['stepNs'])
            for key in ('inputRiseDelayNs','inputFallDelayNs','sourceToOutputLowNs'):
                self.assertLess(max(abs(x-y) for x,y in zip(a[key],b[key])),.5)
        self.assertGreater(max(r['maximumSinkA'] for r in report['runs']),.0018)


if __name__=='__main__':unittest.main()
