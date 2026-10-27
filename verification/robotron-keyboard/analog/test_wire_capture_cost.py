import copy,json,shutil,tempfile,unittest
from pathlib import Path
from wire_capture_cost import HERE,review
from retained_evidence import check
from ttl7406_probe import sha
ROOT=HERE/'reports/wire-capture-cost'

class WireCaptureCostTests(unittest.TestCase):
    def test_retained_costs_are_not_semantic_acceptance(self):
        check(ROOT);r=review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertFalse(r['semanticAcceptanceEstablished']);self.assertEqual(len(r['runs']),8)
        self.assertEqual(r['runs']['observe']['logicalLogBytes'],9799026287)
        self.assertGreater(r['runs']['observe']['captureAndChecksSeconds'],r['runs']['observe']['producerSeconds'])
    def test_incomplete_over_budget_and_invalid_times_reject(self):
        changes=[lambda r:r.update(completed=False),lambda r:r['log'].update(bytes=13*1024**3),lambda r:r['log'].update(elapsedSeconds=float('nan')),lambda r:r.update(elapsedSeconds=1),lambda r:r.update(exitCode=2)]
        for mutate in changes:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'observe/run.json';r=json.loads(p.read_text());mutate(r);p.write_text(json.dumps(r))
                identity=root/'capture-identities.json';ids=json.loads(identity.read_text());ids['observe']['receiptSha256']=sha(p);identity.write_text(json.dumps(ids))
                with self.assertRaises(ValueError):review(root)
    def test_log_size_identity_mismatch_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'capture-identities.json';r=json.loads(p.read_text());r['observe']['compressedLogBytes']-=1;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'compressed log identity'):review(root)

if __name__=='__main__':unittest.main()
