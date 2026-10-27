import copy,json,shutil,tempfile,unittest
from pathlib import Path
import arithmetic_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/arithmetic-state'

class ArithmeticProbe(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(probe.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def mutate(self,filename,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/filename;p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_partial_input_is_not_merge(self):
        # Both snapshots must change together so the stimulus oracle, not the
        # observer idempotence comparison, detects the wrong partial semantics.
        self.mutate('enabled.stdout',lambda s:s.replace('2'*71+'3'+'2'*8,'0'*71+'3'+'0'*8),'stimulus oracle')
    def test_case_equality_and_unknowns(self):
        self.assertEqual(probe.output(3,'23','23'),'3')
        self.assertEqual(probe.output(4,'23','23'),'1')
        self.assertEqual(probe.output(5,'23','23'),'0')
        self.assertEqual(probe.output(3,'13','03'),'0')
        self.mutate('disabled.stdout',lambda s:s.replace('ARITHMETIC_VALUE 5000 3 1','ARITHMETIC_VALUE 5000 3 0'),'independent oracle')
    def test_missing_fault_restoration(self):
        self.mutate('corrupt.stdout',lambda s:s.replace('ARM_RESTORED','ARM_MISSING',1),'Expected ARM_RESTORED')
    def test_fault_rejects_unrelated_changes(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();a=lines.index('VAR_BEGIN 1 0');b=next(i for i in range(a,len(lines)) if lines[i].startswith('VAR_END '))
        before=probe.parse(lines[a:b+1])
        for n in before['nodes']:
            for field in range(4):
                after=copy.deepcopy(before);v=next(v for v in after['nodes'] if v['id']==n['id'])
                if field==3:v['width']^=1
                else:v['vectors'][field]='1'+v['vectors'][field][1:]
                probe.changed(before,after,n['id'],field)
                after['tick']+=1
                with self.assertRaisesRegex(ValueError,'unrelated'):probe.changed(before,after,n['id'],field)

if __name__=='__main__':unittest.main()
