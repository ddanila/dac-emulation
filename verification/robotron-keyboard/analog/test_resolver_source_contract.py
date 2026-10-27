import json,unittest
from pathlib import Path
from resolver_source_contract import layout,profile
from retained_evidence import check
HERE=Path(__file__).resolve().parent

class ResolverOwnership(unittest.TestCase):
    def test_retained_board_profile(self):
        root=HERE/'reports/resolver-source-contract';check(root)
        report=json.loads((root/'assessment.json').read_text());board=HERE/'reports/concat-board-budget'
        self.assertEqual(profile((board/'board.vvp').read_text(),json.loads((board/'assessment.json').read_text())['nativeClasses']['fun']),report['compiledProfile'])
        self.assertFalse(report['qualified'])
    def test_tree_boundaries(self):
        for ports,counts in [(1,[1]),(2,[2,1]),(4,[4,1]),(5,[5,2,1]),(16,[16,4,1]),(17,[17,5,2,1]),(65,[65,17,5,2,1])]:
            result=layout(ports);self.assertEqual([l['count'] for l in result['levels']],counts)
            self.assertEqual(result['slots'],sum(counts));self.assertEqual(result['outputIndex'],sum(counts)-1)
            self.assertEqual([l['base'] for l in result['levels']],[sum(counts[:i]) for i in range(len(counts))])
        for bad in (0,-1,True,1.5):
            with self.assertRaises(ValueError):layout(bad)
    def test_extensions_and_pulls(self):
        text='a .resolv tri0, a0, a1, a2, a3, a4;\nb .resolv tri1, b0;\n'
        p=profile(text,{'resolv_tri':2,'resolv_extend':1,'unrelated':9})
        self.assertEqual(p['resolvers'][0]['layout']['extensionBases'],[4]);self.assertEqual(p['totalCacheSlots'],9)
        with self.assertRaisesRegex(ValueError,'population'):profile(text,{'resolv_tri':2})
    def test_unknown_or_malformed_population(self):
        for text,classes in [('a .resolv custom, b;',{'resolv_tri':1}),('a .resolv tri, b;\na .resolv tri, b;',{'resolv_tri':2}),('a .resolv tri, b;',{'resolv_tri_extra':1}),('a .resolv tri, b;',{'resolv_tri':True})]:
            with self.assertRaises(ValueError):profile(text,classes)

if __name__=='__main__':unittest.main()
