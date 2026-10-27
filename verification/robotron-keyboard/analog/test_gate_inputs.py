"""Input-path evidence separates runtime fidelity from unequal-width semantics."""
import json,shutil,tempfile,unittest
from pathlib import Path
import gate_input_probe as gate
ROOT=Path(__file__).resolve().parent/'reports/gate-inputs'

class GateInputs(unittest.TestCase):
    def test_retained(self):
        result=gate.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(result['unequalWidthControllingDiscontinuityObserved'])
    def mutate(self,mode,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/(mode+'.stdout');p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):gate.review(root)
    def test_wrong_rounding_output(self):
        self.mutate('baseline',lambda s:s.replace('GATE_VALUE 1000 6 1','GATE_VALUE 1000 6 0'),'oracle')
    def test_unequal_width_discontinuity_not_silently_normalized(self):
        self.mutate('disabled',lambda s:s.replace('GATE_VALUE 6000 0 00'+'3'*78,'GATE_VALUE 6000 0 '+'0'*80),'oracle')
    def test_nonfinite_cache_not_assumed_zero(self):
        def change(s):
            lines=s.splitlines();tick=0
            for i,line in enumerate(lines):
                if line.startswith('VGL_BEGIN '):tick=int(line.split()[2])
                if tick==7000 and line.startswith('VGL_GATE '):
                    row=line.split();row[10]='0';lines[i]=' '.join(row)
            return '\n'.join(lines)+'\n'
        self.mutate('enabled',change,'input-path oracle')

if __name__=='__main__':unittest.main()
