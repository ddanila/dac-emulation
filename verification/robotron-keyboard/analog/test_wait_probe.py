import copy,unittest,tempfile,shutil
from pathlib import Path
from wait_probe import review,parse_snapshot,validate,changed_snapshot
SOURCE=Path(__file__).resolve().parent/'reports/wait-event'

class WaitProbe(unittest.TestCase):
    def snapshot(self):
        lines=(SOURCE/'enabled.stdout').read_text().splitlines();start=lines.index('VWM_BEFORE')+1
        end=next(i for i in range(start,len(lines)) if lines[i].startswith('VT_END '))
        return parse_snapshot(lines[start:end+1])

    def test_real_controls(self):
        result=review(SOURCE)
        self.assertTrue(result['normalStateTrajectoryExactlyEqual'])
        self.assertTrue(all(result['faultsByField'].values()))

    def test_missing_duplicate_waiter_and_unrelated_fault(self):
        before=self.snapshot();validate(before)
        bad=copy.deepcopy(before);target=next(e for e in bad['events'] if e['thread']);target.update(thread=0,head=0)
        with self.assertRaises(ValueError):validate(bad)
        changed_snapshot(before,bad,0)
        bad['threads']['threads'][0]['pc']=0
        with self.assertRaises(ValueError):changed_snapshot(before,bad,0)
        bad=copy.deepcopy(before);target=next(e for e in bad['events'] if e['thread']);bad['events'].append(copy.deepcopy(target))
        with self.assertRaises(ValueError):validate(bad)

    def test_missing_cache_fault_and_changed_continuation(self):
        for old,new in [('VWE_CACHE 3 0 0 -','VWE_CACHE 3 0 1 0'),('VWM_FAULT 3 1 1','VWM_FAULT 3 0 1'),('AUTO_NAMED 4000','AUTO_NAMED 4001')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)/'controls';shutil.copytree(SOURCE,root)
                p=root/'corrupt.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
