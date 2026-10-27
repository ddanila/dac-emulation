import copy,json,shutil,tempfile,unittest
from pathlib import Path
import memory_board_budget as board
from memory_metadata import HERE,parse
from array_probe import parse as array_parse
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
from retained_evidence import check
ROOT=HERE/'reports/memory-board-budget'

class MemoryBoardTests(unittest.TestCase):
    def inputs(self):
        return [parse((ROOT/'memories-before.txt').read_text().splitlines()),array_parse((ROOT/'memory-arrays-before.txt').read_text().splitlines()),metadata_parse((ROOT/'metadata-before.txt').read_text().splitlines()),reference_parse((ROOT/'metadata-references-before.txt').read_text().splitlines()),(ROOT/'io.vvp').read_text(),board.native_layout(ROOT)]
    def test_retained_board_bindings(self):
        check(ROOT);r=board.review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(r['bindings']['memories'],3);self.assertEqual(r['bindings']['logicalBits'],16512);self.assertEqual(r['bindings']['readPorts'],23)
    def test_identity_name_owner_range_and_population_reject(self):
        mutations=[lambda a:a[0]['rows'].pop(),lambda a:a[0]['rows'][0].update(name=b'bad\0'.hex()),lambda a:a[0]['rows'][0].update(scope=a[0]['rows'][1]['scope']),lambda a:a[0]['rows'][1].update(array=a[0]['rows'][2]['array']),lambda a:a[0]['rows'][0].update(handle=a[0]['rows'][0]['handle']+1),lambda a:a[1]['arrays'][0].update(signed=1),lambda a:a[1]['arrays'][0].update(first=1,last=2048),lambda a:a[1]['ports'].pop(),lambda a:a[3]['objects'].__setitem__(next(i for i,o in enumerate(a[3]['objects']) if o['type']==29),dict(id=999999,pointer=1,type=29))]
        for mutate in mutations:
            a=self.inputs();mutate(a)
            with self.assertRaises(ValueError):board.bindings(*a)
    def test_same_shape_bank_crosslink_rejects(self):
        a=self.inputs();rows=a[0]['rows'];rows[1]['array'],rows[2]['array']=rows[2]['array'],rows[1]['array']
        with self.assertRaisesRegex(ValueError,'layout differs'):board.bindings(*a)
    def test_changed_scan_and_invalid_timing_reject(self):
        for name,content in (('memories-after.txt','changed'),('memories-budget.txt','SCOPE_SCAN memories 64 nan 1 2\n')):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);(root/name).write_text(content)
                with self.assertRaises(ValueError):board.review(root)

if __name__=='__main__':unittest.main()
