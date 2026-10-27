import json,shutil,tempfile,unittest
from pathlib import Path
from postreset_drain_diagnostic_evidence import review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/postreset-drain-refinements'

class DrainDiagnosticEvidenceTests(unittest.TestCase):
    def test_retained_failure_is_not_reclassified_as_acceptance(self):
        check(ROOT);r=review(ROOT);self.assertFalse(r['refinementGatePassed']);self.assertFalse(r['semanticReplayPerformed']);self.assertEqual(len(r['failureSignals']),5)
    def test_changed_acceptance_or_missing_level_reject(self):
        for change in ('acceptance','level'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'assessment.json';r=json.loads(p.read_text())
                if change=='acceptance':r['refinementGatePassed']=True
                else:r['receipts'].pop('finest')
                p.write_text(json.dumps(r))
                with self.assertRaises(ValueError):review(root)
    def test_changed_archive_identity_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'retention.json';r=json.loads(p.read_text());key=next(iter(r['archives']));fake=root/'fake.xz';fake.write_bytes(b'x');r['archives'][key]['path']=str(fake);p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'Changed local archive'):review(root,True)

    def test_retained_maximum_brackets(self):
        from postreset_drain_maxima_review import review as maxima
        self.assertEqual(maxima(ROOT),json.loads((ROOT/'maxima-review.json').read_text()))
    def test_changed_bracket_value_reject(self):
        from postreset_drain_maxima_review import review as maxima
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'maxima.json';r=json.loads(p.read_text());key=next(iter(r['witnesses']));r['witnesses'][key]['left']['after'][1]+=.01;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'interpolation'):maxima(root)

if __name__=='__main__':unittest.main()
