import copy,tempfile,unittest
from pathlib import Path
from island_probe import review,parse_snapshot,validate_normal,changed_snapshot,fixture_state
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'reports/island-payload'

class IslandProbe(unittest.TestCase):
    def snapshot(self):
        lines=(SOURCE/'enabled.stdout').read_text().splitlines();a=next(i for i,l in enumerate(lines) if l.startswith('VI_BEGIN '));b=next(i for i in range(a,len(lines)) if lines[i].startswith('VI_END '))
        return parse_snapshot(lines[a:b+1])

    def test_real_runtime_evidence(self):
        self.assertEqual(review(SOURCE)['restoredFaults'],42)
        snapshot=self.snapshot();validate_normal(snapshot);fixture_state(snapshot,0)

    def test_cross_port_mesh_and_unrelated_fault_rejected(self):
        before=self.snapshot();bad=copy.deepcopy(before);bad['islands'][0]['branches'][0]['links'][0][1]=1
        with self.assertRaises(ValueError):validate_normal(bad)
        changed_snapshot(before,bad,5)
        bad['islands'][0]['flag']=1
        with self.assertRaises(ValueError):changed_snapshot(before,bad,5)
        bad=copy.deepcopy(before);bad['islands'][0]['ports'][1]['vectors']['out']['bits']='166'*4
        with self.assertRaises(ValueError):fixture_state(bad,0)

    def test_missing_fault_and_truncated_snapshot_rejected(self):
        for old,new in [('VIM_FAULT 4 1 1','VIM_FAULT 4 0 1'),('VI_VECTOR scratch 0 -','VI_VECTOR scratch 1 -'),('VIM_RESTORED','VIM_MISSING')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)
                for name in ('baseline','disabled','enabled','corrupt'):
                    for suffix in ('stdout','stderr'):
                        text=(SOURCE/(name+'.'+suffix)).read_text()
                        if name=='corrupt':text=text.replace(old,new,1)
                        (root/(name+'.'+suffix)).write_text(text)
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
