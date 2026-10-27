import copy,json,unittest
from pathlib import Path
from scope_signal_declarations import HERE,compiled_signals,state,validate,review
from scope_signal_declaration_contract import assess
from retained_evidence import check
from ttl7406_probe import sha
ROOT=HERE/'reports/scope-signal-declarations'
BOARD=HERE/'reports/scope-signals/board-budget'

class ScopeSignalDeclarationTests(unittest.TestCase):
    def test_retained_complete_board(self):
        check(ROOT);check(HERE/'reports/scope-signals')
        inputs=json.loads((ROOT/'inputs.json').read_text())
        self.assertEqual(sha(HERE/'reports/scope-signals/manifest.json'),inputs['retainedManifestSha256'])
        for name,digest in inputs['files'].items():self.assertEqual(sha(HERE/name),digest)
        self.assertEqual(review(BOARD),json.loads((ROOT/'assessment.json').read_text()))
    def test_metadata_and_population_mutations_reject(self):
        original=state(BOARD);compiled=(BOARD/'io.vvp').read_text()
        mutations=[lambda s:s['signals']['rows'].pop()]
        for key,value in (('signed',1),('msb',999),('lsb',999),('kind','14signal_integer'),('name','5800')):
            mutations.append(lambda s,k=key,v=value:s['signals']['rows'][0].update({k:v}))
        for mutate in mutations:
            bad=copy.deepcopy(original);mutate(bad)
            with self.assertRaises(ValueError):validate(bad,compiled)
    def test_compiled_mutations_reject(self):
        original=state(BOARD);compiled=(BOARD/'io.vvp').read_text()
        for old,new in (('.net "bus_high", 23 0','.net/s "bus_high", 23 0'),('.net "bus_high", 23 0','.net "bus_high", 24 0'),('.net "bus_high", 23 0','.net *"bus_high", 23 0'),('.net "bus_high", 23 0','.net/r "bus_high", 23 0')):
            self.assertIn(old,compiled)
            with self.assertRaises(ValueError):validate(original,compiled.replace(old,new,1))
    def test_hierarchy_scope_recall_and_signed_bounds(self):
        text='''S0 .scope module, "top" "top" 1 1;
v0 .var/s "a", -2 -5;
vh .net/2u *"temporary", 0 0, L0;
S1 .scope begin, "child" "child" 1 2, S0;
v1 .var/i "a", 31 0;
.scope S0;
v2 .net8 "b", 0 7, L1;
'''
        rows,hidden=compiled_signals(text);self.assertEqual(hidden,1);self.assertEqual(len(rows),3)
        self.assertEqual(rows[(('top',),'a')],dict(kind='10signal_reg',signed=1,msb=-2,lsb=-5))
        self.assertEqual(rows[(('top','child'),'a')]['kind'],'14signal_integer')
        self.assertEqual(rows[(('top',),'b')]['lsb'],7)
        for suffix in ('v3 .var "a", 0 0;','.scope UNKNOWN;','v3 .var/2u "c", 0 0;'):
            with self.assertRaises(ValueError):compiled_signals(text+suffix)
    def test_compiler_source_contract(self):
        archive=Path('/private/tmp/k7658-icarus-pinned.tar.gz')
        if not archive.is_file():self.skipTest('Pinned native archive unavailable')
        self.assertEqual(assess(archive),json.loads((ROOT/'source-contract.json').read_text()))

if __name__=='__main__':unittest.main()
