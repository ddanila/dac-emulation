import copy,json,shutil,tempfile,unittest
from pathlib import Path
from parameter_board_budget import review,bindings,compiled_parameters
from parameter_payload import parse
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/parameter-board-budget'

class ParameterBoardBudgetTests(unittest.TestCase):
    def test_retained_complete_board(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(review(ROOT)['bindings']['parameters'],56)
    def test_fields_values_ownership_and_population_reject(self):
        payload=parse((ROOT/'parameters-before.txt').read_text().splitlines());metadata=metadata_parse((ROOT/'metadata-before.txt').read_text().splitlines());reference=reference_parse((ROOT/'metadata-references-before.txt').read_text().splitlines());compiled=(ROOT/'io.vvp').read_text()
        mutations=[lambda r:r['rows'].pop(),lambda r:r['rows'][0]['value']['words'][0].__setitem__(0,r['rows'][0]['value']['words'][0][0]^1),lambda r:r['rows'][0]['value'].update(sized=1),lambda r:r['rows'][0].update(scope=1)]
        for key in ('local','file','line'):
            mutations.append(lambda r,k=key:r['rows'][0].update({k:r['rows'][0][k]^1}))
        for mutate in mutations:
            bad=copy.deepcopy(payload);mutate(bad)
            with self.assertRaises(ValueError):bindings(bad,metadata,reference,compiled)
    def test_compiler_local_signed_xz_and_recalled_scope(self):
        text='''S0 .scope module, "top" "top" 1 1;
P0 .param/l "P" 1 2 3, +C4<10xz>;
S1 .scope begin, "child" "child" 1 2, S0;
P1 .param/l "P" 0 2 4, C4<1>;
.scope S0;
P2 .param/l "Q" 0 2 5, C4<0>;
'''
        rows=compiled_parameters(text);self.assertEqual(len(rows),3)
        self.assertEqual(rows[(('top',),'P')],dict(local=1,file=2,line=3,signed=1,sized=0,bits=[2,3,0,1]))
        for suffix in ('P3 .param/l "P" 0 2 3, C4<0>;','P3 .param/real "R" 0 2 3, Cr<m3ff0000000000000g000>;','.scope missing;'):
            with self.assertRaises(ValueError):compiled_parameters(text+suffix)
    def test_changed_image_or_nonfinite_time_reject(self):
        for filename in ('parameters-after.txt','parameters-budget.txt'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/filename;s=p.read_text()
                if filename.endswith('budget.txt'):
                    a=s.split();a[3]='nan';p.write_text(' '.join(a)+'\n')
                else:p.write_text(s.replace('VPM_BEGIN 1 0','VPM_BEGIN 1 1',1))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
