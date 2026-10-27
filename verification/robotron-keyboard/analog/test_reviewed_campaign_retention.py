import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import reviewed_campaign_retention as r

class RetentionTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'capture';(source/'off').mkdir(parents=True);(source/'off/run.json').write_text('{"completed": true}');(source/'off/data.txt').write_text('captured')
        assessment=root/'assessment.json';assessment.write_text(json.dumps(dict(controlsPassed=True,reviewCompleted=True,firmwareRecordsExactlyEqual=True,receipts={'off':r.sha(source/'off/run.json')})))
        producer=root/'producer.py';producer.write_text('# capture\n');sources={'reviewed_campaign_retention.py':r.sha(Path(r.__file__))}
        return source,assessment,producer,sources
    def test_budget_reports_remain_separate_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,assessment,producer,sources=self.fixture(root)
            for stage in ('wire','signal','mux'):
                budget=root/(stage+'-board-budget');budget.mkdir();(budget/'assessment.json').write_text('existing initialized evidence')
                out=r.destination(root,stage);self.assertNotEqual(out,budget)
                r.retain(source,assessment,producer,out,sources);r.check(out)
                self.assertEqual((budget/'assessment.json').read_text(),'existing initialized evidence')
                self.assertEqual((out/'off/data.txt').read_text(),'captured')
                with self.assertRaises(ValueError):r.destination(root,stage)
                with self.assertRaises(ValueError):r.retain(source,assessment,producer,out,sources)
    def test_partial_review_or_changed_receipt_refuses_before_copy(self):
        for fault in ('review','receipt'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source,assessment,producer,sources=self.fixture(root);out=r.destination(root,'wire')
                if fault=='review':
                    d=json.loads(assessment.read_text());d['reviewCompleted']=False;assessment.write_text(json.dumps(d))
                else:(source/'off/run.json').write_text('{}')
                with self.assertRaises(ValueError):r.retain(source,assessment,producer,out,sources)
                self.assertFalse(out.exists())
    def test_copy_difference_cannot_be_manifested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,assessment,producer,sources=self.fixture(root);out=r.destination(root,'signal');original=r.shutil.copytree
            def corrupt(a,b):
                with patch.object(r.shutil,'copytree',original):original(a,b)
                (b/'off/data.txt').write_text('changed')
            with patch.object(r.shutil,'copytree',side_effect=corrupt),self.assertRaises(ValueError):r.retain(source,assessment,producer,out,sources)
            self.assertFalse((out/'manifest.json').exists())

if __name__=='__main__':unittest.main()
