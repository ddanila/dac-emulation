import copy,shutil,tempfile,unittest
from pathlib import Path
from thread_lifecycle_probe import review,parse_snapshot,validate,changed_snapshot,target,FIELDS
SOURCE=Path(__file__).resolve().parent/'reports/thread-lifecycle'

class ThreadLifecycle(unittest.TestCase):
    def snapshots(self):
        lines=(SOURCE/'enabled.stdout').read_text().splitlines();result=[]
        for start,line in enumerate(lines):
            if line!='VTM_BEFORE':continue
            end=next(i for i in range(start+1,len(lines)) if lines[i].startswith('VTQ_END '))
            result.append(parse_snapshot(lines[start+1:end+1]))
        return result

    def test_native_lifecycle_and_cleanup(self):
        result=review(SOURCE)
        self.assertTrue(result['normalStateTrajectoryExactlyEqual'])
        self.assertIn('storage-reused-with-fresh-identity',result['observedStateFamilies'])

    def test_deletion_queue_requires_actual_delay_flag(self):
        before=self.snapshots()[2];validate(before)
        deletion=next(e for e in before['queue']['events'] if e['kind']==2)
        bad=copy.deepcopy(before);t=next(t for t in bad['threads']['threads'] if t['id']==deletion['thread'])
        t['state']=t['state'][:8]+'0'
        with self.assertRaises(ValueError):validate(bad)
        changed_snapshot(before,bad,9)
        self.assertEqual(before['threads']['threads'][target(before,9)]['id'],deletion['thread'])
        bad['queue']['events'][0]['key']+=1
        with self.assertRaises(ValueError):changed_snapshot(before,bad,9)

    def test_missing_fault_and_unexpected_child_continuation(self):
        for old,new in [('VTM_FAULT 9 1 1','VTM_FAULT 9 0 1'),('FINISHED 17000','UNEXPECTED_A')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)/'controls';shutil.copytree(SOURCE,root)
                p=root/'corrupt.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
