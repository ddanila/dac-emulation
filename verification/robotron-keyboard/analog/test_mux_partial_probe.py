"""Direct partial mux evidence must cover silent caches and exact continuation."""
import json,shutil,tempfile,unittest
from pathlib import Path
import mux_partial_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/mux-partial'

class PartialMux(unittest.TestCase):
    def test_retained(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(result['directPartialPorts'],[0,1,2])
        self.assertTrue(all(result['faultsByField'].values()))

    def reject_mutation(self,mutate,pattern):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'enabled.stdout';p.write_text(mutate(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)

    def test_missing_direct_call(self):
        self.reject_mutation(lambda s:s.replace('PARTIAL_CALL 2 1 70 2301\n',''), 'oracle')

    def test_wrong_output(self):
        self.reject_mutation(lambda s:s.replace('PARTIAL_VALUE 1000 0','PARTIAL_VALUE 1000 1'), 'oracle')

    def test_silent_cache_corruption(self):
        def mutate(s):
            lines=s.splitlines();tick=None
            for i,line in enumerate(lines):
                if line.startswith('VXM_BEGIN '):tick=int(line.split()[2])
                if tick==2000 and line.startswith('VXM_MUX '):
                    row=line.split();row[11]=row[11][:70]+'1'+row[11][71:];lines[i]=' '.join(row)
            return '\n'.join(lines)+'\n'
        self.reject_mutation(mutate,'partial cache')

    def test_missing_restoration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'corrupt.stdout';p.write_text(p.read_text().replace('MXM_FAULT 0 1 1','MXM_FAULT 0 1 0',1))
            with self.assertRaisesRegex(ValueError,'MXM_FAULT'):probe.review(root)

if __name__=='__main__':unittest.main()
