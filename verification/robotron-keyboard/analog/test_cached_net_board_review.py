import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import cached_net_board_review as reviewer
from cached_net_board_review import ExactBundleCache


class ExactCacheTests(unittest.TestCase):
    def test_exact_inputs_identity_changes_and_return_isolation(self):
        calls=[]
        def parse(lines,identities):
            calls.append(1)
            return {'lines':list(lines),'identity':dict(identities)}
        cached=ExactBundleCache(parse);lines=['one','two'];identities={'module':1}
        result=cached(lines,identities);result['lines'].append('corruption');result['identity']['module']=9
        self.assertEqual(cached(lines,identities),{'lines':lines,'identity':identities})
        self.assertEqual(len(calls),1)
        lines[0]='changed';self.assertEqual(cached(lines,identities)['lines'][0],'changed')
        identities['module']=2;self.assertEqual(cached(lines,identities)['identity']['module'],2)
        self.assertEqual(len(calls),3)
        self.assertEqual((cached.hits,cached.misses),(1,3))

    def test_invalid_records_still_refuse_on_each_attempt(self):
        def parse(lines,identities):
            if lines!=['valid']:raise ValueError('Malformed snapshot')
            return {'accepted':True}
        cached=ExactBundleCache(parse);cached(['valid'],{})
        for _ in range(2):
            with self.assertRaises(ValueError):cached(['invalid'],{})
        self.assertEqual(cached(['valid'],{}),{'accepted':True})
        self.assertEqual((cached.hits,cached.misses),(1,1))

class AssessmentComparisonTests(unittest.TestCase):
    def test_json_key_conversion_matches_retained_representation(self):
        actual={'waitEventKinds':{1:3,2:9},'controlsPassed':True}
        with tempfile.TemporaryDirectory() as tmp:
            reference=Path(tmp)/'reference.json';reference.write_text(json.dumps(actual))
            original=reviewer.original.bundle
            with patch.object(reviewer.original,'assess',return_value=actual):
                result=reviewer.run(Path(tmp),Path(tmp)/'producer.py',reference)
            self.assertTrue(result['completeAssessmentExactlyEqual'])
            self.assertIs(reviewer.original.bundle,original)
    def test_real_difference_retains_failed_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            reference=Path(tmp)/'reference.json';reference.write_text('{"count": 1}')
            diagnostic=Path(tmp)/'mismatch.json'
            with patch.object(reviewer.original,'assess',return_value={'count':2}):
                with self.assertRaises(ValueError):reviewer.run(Path(tmp),Path(tmp)/'producer.py',reference,diagnostic)
            result=json.loads(diagnostic.read_text())
            self.assertFalse(result['completed']);self.assertFalse(result['completeAssessmentExactlyEqual'])
            self.assertEqual(result['assessment'],{'count':2})


if __name__=='__main__':unittest.main()
