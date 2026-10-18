"""Reject incomplete or contradictory device evidence before expensive oscillator runs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from oscillator_family_probe import candidates, sha


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root/'candidate'
        self.folder.mkdir()
        (self.folder/'candidate.cir').write_text('* synthetic model\n')
        identity = sha(self.folder/'candidate.cir')
        self.reports = {
            'dc': {'completed': True, 'outputLimitsPassed': True, 'modelSha256': identity},
            'validation': {'completed': True, 'limitsPassed': True, 'sources': {'candidate.cir': identity}},
            'switching': {'completed': True, 'withinDelayLimits': True, 'numericallyConverged': True,
                          'sources': {'candidate.cir': identity}}}
        self.row = dict(name='candidate', modelSha256=identity, dcOutputLimitsPassed=True,
                        additionalDcLimitsPassed=True, switchingLimitsPassed=True, switchingConverged=True)
        self.screen = {'completed': True, 'candidates': [self.row]}
        self.write_reports()

    def write_reports(self):
        for label, report in self.reports.items():
            folder = self.folder/label
            folder.mkdir(exist_ok=True)
            path = folder/('report.json' if label == 'switching' else 'assessment.json')
            path.write_text(json.dumps(report))
            self.row[label+'ReportSha256'] = sha(path)

    def test_complete_evidence_is_admitted(self):
        admitted, rejected = candidates(self.root, self.screen)
        self.assertEqual([row['name'] for row in admitted], ['candidate'])
        self.assertEqual(rejected, [])
        self.assertEqual(admitted[0]['deviceReports']['dcReportSha256'], self.row['dcReportSha256'])

    def test_every_required_summary_gate_is_explicitly_true(self):
        for key in ['dcOutputLimitsPassed', 'additionalDcLimitsPassed', 'switchingLimitsPassed', 'switchingConverged']:
            for value in [False, None, 1, 'true']:
                with self.subTest(key=key, value=value):
                    screen = copy.deepcopy(self.screen)
                    screen['candidates'][0][key] = value
                    admitted, rejected = candidates(self.root, screen)
                    self.assertEqual(admitted, [])
                    self.assertIn(key, rejected[0]['failedOrMissingChecks'])

    def test_hashed_but_incomplete_or_failing_reports_are_rejected(self):
        for label, key in [('dc', 'completed'), ('validation', 'completed'), ('switching', 'completed'),
                           ('dc', 'outputLimitsPassed'), ('validation', 'limitsPassed'),
                           ('switching', 'withinDelayLimits'), ('switching', 'numericallyConverged')]:
            with self.subTest(label=label, key=key):
                self.reports[label][key] = False
                self.write_reports()
                with self.assertRaisesRegex(ValueError, 'Incomplete|contradicts'):
                    candidates(self.root, self.screen)
                self.reports[label][key] = True
        self.write_reports()

    def test_report_for_another_model_is_rejected_even_with_valid_hash(self):
        self.reports['switching']['sources']['candidate.cir'] = 'another model'
        self.write_reports()
        with self.assertRaisesRegex(ValueError, 'model differs'):
            candidates(self.root, self.screen)

    def test_changed_capture_and_failed_probe_are_rejected(self):
        (self.folder/'dc/assessment.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Changed candidate evidence'):
            candidates(self.root, self.screen)
        self.write_reports()
        self.row['probes'] = {'dc': {'exitCode': 1}}
        with self.assertRaisesRegex(ValueError, 'probe failed'):
            candidates(self.root, self.screen)

    def test_incomplete_screen_is_rejected(self):
        self.screen['completed'] = False
        with self.assertRaisesRegex(ValueError, 'Incomplete parameter screen'):
            candidates(self.root, self.screen)


if __name__ == '__main__':
    unittest.main()
