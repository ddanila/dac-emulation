import copy,shutil,tempfile,unittest
from pathlib import Path
from code_binding_probe import review,parse_snapshot,validate,changed_snapshot
SOURCE=Path(__file__).resolve().parent/'reports/code-binding'

class CodeBinding(unittest.TestCase):
    def snapshot(self):
        lines=(SOURCE/'enabled.stdout').read_text().splitlines();start=lines.index('VTM_BEFORE')+1
        end=next(i for i in range(start,len(lines)) if lines[i].startswith('VTC_END '))
        return parse_snapshot(lines[start:end+1])

    def test_native_cross_chunk_and_address_controls(self):
        result=review(SOURCE)
        self.assertTrue(result['normalStateTrajectoryExactlyEqual'])
        self.assertTrue(all(result['faultsByField'].values()))

    def test_foreign_pc_missing_binding_and_opcode_rejected(self):
        before=self.snapshot();validate(before)
        bad=copy.deepcopy(before);bad['threads']['threads'][0]['pc']=1;bad['code'][0].update(pc=1,code=0,opcode=0)
        with self.assertRaises(ValueError):validate(bad)
        changed_snapshot(before,bad,11)
        bad['threads']['threads'][0]['scope']=0
        with self.assertRaises(ValueError):changed_snapshot(before,bad,11)
        for mode in ('missing','opcode','mismatch'):
            bad=copy.deepcopy(before)
            if mode=='missing':bad['code'].clear()
            elif mode=='opcode':bad['code'][0]['opcode']=0
            else:bad['code'][0]['pc']+=1
            with self.assertRaises(ValueError):validate(bad)

    def test_false_address_acceptance_missing_fault_and_continuation(self):
        for old,new in [('foreign=1','foreign=0'),('VTM_FAULT 11 1 1','VTM_FAULT 11 0 1'),('VALUE 1000 512','VALUE 1000 511')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)/'controls';shutil.copytree(SOURCE,root)
                p=root/'corrupt.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
