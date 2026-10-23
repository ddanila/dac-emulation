#!/usr/bin/env python3
"""Guard the frozen live numerical witness without rerunning the firmware."""
import hashlib
import json
import lzma
from pathlib import Path
import re
import unittest
from linear_system_review import parse
from truncation_arithmetic_review import review_record
from analog_driver_replay import recorded_trtol
from live_prefix_review import compare

ROOT=Path(__file__).parent/'reports/live-state'

class LiveStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'assessment.json').read_text())
        cls.data=(ROOT/'ngspice.log.xz').read_bytes()
        cls.log=lzma.decompress(cls.data).decode()

    def test_retained_artifacts(self):
        manifest=json.loads((ROOT/'manifest.json').read_text())
        for name,digest in manifest.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
        for name,digest in self.report['sources'].items():
            self.assertEqual(hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(),digest,name)

    def test_completed_prefix_is_not_qualification(self):
        expected=json.loads((ROOT/'prefix-comparison.json').read_text())
        actual=compare([ROOT/'live-state-prefix25/witness.txt.xz',ROOT/'live-state-prefix12-step/witness.txt.xz'])
        self.assertEqual(actual,expected)
        self.assertFalse(actual['qualified'])
        self.assertGreater(actual['maximumAbsoluteDifferences']['v(bus_high_9)'],1)

    def test_frozen_evidence(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),self.report['logSha256'])
        systems,incomplete=parse(self.log)
        self.assertEqual(incomplete,self.report['incompleteSystemIdsExcluded'])
        for result in self.report['linearSystems']:
            system=next(s for s in systems if s['id']==result['id'])
            self.assertEqual(system['metadata'],result['metadata'])
        self.assertIn('STATE_AUDIT accepted ',self.log)
        self.assertFalse(self.report['qualified'])

    def test_exact_estimator_does_not_remove_collapse(self):
        records=[dict(re.findall(r'(\w+)=([^\s]+)',line)) for line in self.log.splitlines()
                 if line.startswith('TRUNC_AUDIT error ')]
        last=review_record(records[-1],1e-15,recorded_trtol(self.log))
        self.assertEqual(last,self.report['lte'][-1])
        self.assertLess(last['exactHistoryProposalSeconds'],last['deltaSeconds']*.9)
        self.assertLess(last['proposalRelativeRoundingError'],1e-14)

    def test_terminal_solve_is_not_the_initial_rejection(self):
        first,last=self.report['linearSystems']
        self.assertLess(first['largestSolutionChange'],1e-10)
        self.assertGreater(last['largestSolutionChange'],1e6)
        self.assertLess(last['precisionAgreement'],1e-50)
        current=last['inductorCurrents']['l1.1#branch']
        self.assertGreater(abs(current['recorded']-current['replayed']),8e-7)

if __name__=='__main__':unittest.main()
