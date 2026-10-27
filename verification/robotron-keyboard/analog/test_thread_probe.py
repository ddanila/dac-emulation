import copy,tempfile,unittest
from pathlib import Path
from thread_probe import review,parse_snapshot,validate_normal,changed_snapshot
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'reports/thread-payload'

class ThreadProbe(unittest.TestCase):
    def snapshots(self):
        lines=(SOURCE/'enabled.stdout').read_text().splitlines();result=[]
        for i,line in enumerate(lines):
            if line!='VTM_BEFORE':continue
            end=next(j for j in range(i+1,len(lines)) if lines[j].startswith('VT_END '))
            result.append(parse_snapshot(lines[i+1:end+1]))
        return result

    def test_real_initialized_state_and_restored_faults(self):
        result=review(SOURCE);self.assertTrue(all(result['faultsByField'].values()))
        shots=self.snapshots()
        self.assertTrue(all(t['words']==['-']*16 for t in shots[0]['threads']))
        self.assertTrue(any(v!='-' for s in shots[1:] for t in s['threads'] for v in t['words']))

    def test_wait_cycle_and_unrelated_mutation_rejected(self):
        before=self.snapshots()[0];bad=copy.deepcopy(before);t=bad['threads'][0];t['wait']=t['id']
        with self.assertRaises(ValueError):validate_normal(bad)
        changed_snapshot(before,bad,4)
        t['pc']=0
        with self.assertRaises(ValueError):changed_snapshot(before,bad,4)
        bad=copy.deepcopy(before);bad['threads'][0]['parent']=999
        with self.assertRaises(ValueError):validate_normal(bad)

    def test_fake_initialization_missing_fault_and_continuation_rejected(self):
        for old,new in [('VT_WORDS 16 -','VT_WORDS 16 0000000000000000'),('VTM_FAULT 2 1 1','VTM_FAULT 2 0 1'),('CHILD_B 7000','CHILD_B 7001')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)
                for mode in ('baseline','disabled','enabled','corrupt'):
                    for suffix in ('stdout','stderr'):
                        text=(SOURCE/(mode+'.'+suffix)).read_text()
                        if mode=='corrupt':text=text.replace(old,new,1)
                        (root/(mode+'.'+suffix)).write_text(text)
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
