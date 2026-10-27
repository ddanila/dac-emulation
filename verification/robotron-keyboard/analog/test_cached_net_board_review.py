import unittest
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

if __name__=='__main__':unittest.main()
