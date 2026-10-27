import copy,json,shutil,tempfile,unittest
from pathlib import Path
import island_raw_probe as probe
ROOT=probe.HERE/'reports/island-raw-state'

class IslandRawProbe(unittest.TestCase):
    def test_retained_native_replay(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['liveScratchObservations'],0)
        for field in range(3):self.assertGreater(result['faultsByField'][f'{field}:1'],0)
    def reject(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');text=p.read_text();self.assertIn(old,text);p.write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):probe.review(root)
    def test_original_output_required(self):
        self.reject('baseline','CHANGE 1000 1 1010 1010','CHANGE 1000 1 1010 0101')
    def test_scratch_field_required(self):
        self.reject('enabled','VIR_VECTOR 2','VIR_MISSING 2')
    def test_restoration_required(self):
        self.reject('corrupt','IRM_RESTORED','IRM_NOT_RESTORED')
    def test_callback_identity_required(self):
        text=(ROOT/'enabled.stdout').read_text();line=next(l for l in text.splitlines() if l.startswith('IRM_STAGE ') and l.split()[2]=='1')
        self.reject('enabled',line,line.replace(' 1 1',' 0 1'))
    def test_raw_width_and_port_binding_required(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();a=next(i for i,l in enumerate(lines) if l.startswith('VIR_BEGIN '));b=next(i for i in range(a,len(lines)) if lines[i].startswith('VIR_END '));frame=lines[a:b+1]
        i=next(i for i,l in enumerate(frame) if l.startswith('VIR_VECTOR '));parts=frame[i].split();parts[2]=str(int(parts[2])+1);frame[i]=' '.join(parts)
        with self.assertRaisesRegex(ValueError,'width'):probe.parse(frame)

if __name__=='__main__':unittest.main()
