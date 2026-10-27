import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cached_wire_board_review as r

class CachedWireTests(unittest.TestCase):
    def fixture(self,root):
        (root/'capture').mkdir();(root/'capture/data').write_text('captured')
        producer=root/'producer.py';producer.write_text('# producer\n')
        return root/'capture',producer
    def test_complete_assessment_preserved_and_parser_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);capture,producer=self.fixture(root);original=r.original.bundle
            assessment={'controlsPassed':True,'kinds':{4:7,8:9}}
            def assess(*args):
                first=r.original.bundle(['native'],{'module':1});first['nested'].append(9)
                self.assertEqual(r.original.bundle(['native'],{'module':1}),{'nested':[1]})
                return assessment
            def parser(*args):return {'nested':[1]}
            with patch.object(r.bounded,'budgets'),patch.object(r.original,'bundle',parser),patch.object(r.bounded,'assess',side_effect=assess):
                candidate=r.run(capture,producer);self.assertIs(r.original.bundle,parser)
            self.assertIs(r.original.bundle,original)
            self.assertEqual((candidate['cacheHits'],candidate['cacheMisses']),(1,1));self.assertFalse(candidate['completeAssessmentExactlyEqual'])
            reference=root/'reference.json';reference.write_text(json.dumps(assessment));result=r.compare(candidate,capture,producer,reference)
            self.assertTrue(result['completeAssessmentExactlyEqual']);self.assertFalse(candidate['completeAssessmentExactlyEqual'])
    def test_original_failure_restores_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture,producer=self.fixture(Path(tmp));original=r.original.bundle
            with patch.object(r.bounded,'budgets'),patch.object(r.bounded,'assess',side_effect=ValueError('original refusal')):
                with self.assertRaisesRegex(ValueError,'original refusal'):r.run(capture,producer)
            self.assertIs(r.original.bundle,original)
    def test_changed_evidence_and_real_assessment_difference_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);capture,producer=self.fixture(root)
            with patch.object(r.bounded,'budgets'),patch.object(r.bounded,'assess',return_value={'count':1}):candidate=r.run(capture,producer)
            reference=root/'reference.json';reference.write_text('{"count": 1.0}')
            with self.assertRaisesRegex(ValueError,'differs'):r.compare(candidate,capture,producer,reference)
            reference.write_text('{"count": 1}');(capture/'data').write_text('changed')
            with self.assertRaisesRegex(ValueError,'input evidence'):r.compare(candidate,capture,producer,reference)
    def test_mutation_during_review_cannot_be_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture,producer=self.fixture(Path(tmp))
            def assess(*args):
                (capture/'data').write_text('changed');return {'count':1}
            with patch.object(r.bounded,'budgets'),patch.object(r.bounded,'assess',side_effect=assess):
                with self.assertRaisesRegex(ValueError,'Changed review'):r.run(capture,producer)

if __name__=='__main__':unittest.main()
