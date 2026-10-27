import copy,unittest,tempfile,shutil
from pathlib import Path
from thread_board_review import ThreadLifetimes,queue_snapshot,changed_thread
import test_thread_probe
from thread_compact_probe import expand,review


def state():
    snapshot=copy.deepcopy(test_thread_probe.ThreadProbe().snapshots()[0])
    snapshot['running']=0
    snapshot['threads'][0]['state']='000000010'
    return dict(threads=snapshot,threadQueue=queue_snapshot([
        'VTQ_BEGIN 1 1000','VTQ_EVENT 0 active 0 1 1 2 0x200','VTQ_END 1 0']))


class ThreadBoardReview(unittest.TestCase):
    def test_queue_binding_and_fault_restore_contract(self):
        before=state();tracker=ThreadLifetimes();tracker.observe(before)
        self.assertEqual(tracker.result(True)['queuedThreadObservations'],1)
        changed=copy.deepcopy(before);changed['threadQueue']['events'][0].update(thread=0,key=0)
        changed_thread(before,changed,'queue')
        with self.assertRaises(ValueError):ThreadLifetimes().observe(changed)
        changed['threads']['threads'][0]['pc']=0
        with self.assertRaises(ValueError):changed_thread(before,changed,'queue')

    def test_missing_duplicate_rebound_and_retired_event_rejected(self):
        for mode in ('missing','duplicate','unknown','flag','running'):
            bad=state()
            if mode=='missing':bad['threadQueue']['events']=[]
            elif mode=='duplicate':
                event=dict(bad['threadQueue']['events'][0],id=2,ordinal=1)
                bad['threadQueue']['events'].append(event)
            elif mode=='unknown':bad['threadQueue']['events'][0]['thread']=999
            elif mode=='flag':bad['threads']['threads'][0]['state']='000000000'
            else:bad['threads']['running']=2
            with self.assertRaises(ValueError):ThreadLifetimes().observe(bad)
        tracker=ThreadLifetimes();tracker.observe(state())
        rebound=state();rebound['threadQueue']['events'][0]['key']+=1
        with self.assertRaises(ValueError):tracker.observe(rebound)
        tracker=ThreadLifetimes();tracker.observe(state())
        empty=state();empty['threadQueue']['events']=[];empty['threads']['threads'][0]['state']='000000000'
        tracker.observe(empty)
        with self.assertRaises(ValueError):tracker.observe(state())

    def test_dense_equivalence_cannot_be_omitted_or_changed(self):
        source=Path(__file__).resolve().parent/'reports/thread-compact'
        for mutation in ('missing','changed'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)/'controls';shutil.copytree(source,root)
                p=root/'enabled.stdout';lines=p.read_text().splitlines()
                start=lines.index('VTM_DENSE')
                end=next(i for i in range(start+1,len(lines)) if lines[i].startswith('VT_END '))
                if mutation=='missing':del lines[start:end+1]
                else:
                    i=next(i for i in range(start,end) if lines[i].startswith('VT_FLAGS '))
                    lines[i]=lines[i].replace('-', '0', 1)
                p.write_text('\n'.join(lines)+'\n')
                with self.assertRaises(ValueError):review(root)

    def test_unknown_registers_preserved_and_malformed_sparse_rejected(self):
        result=expand(['VT_FLAGS_SPARSE 512 2 0:0 511:3'])[0].split()[2]
        self.assertEqual(result,'0'+'-'*510+'3')
        for flags in ('2 0:0 0:1','1 512:0','1 -1:0','1 0:4','2 1:0','2 1:0 0:1'):
            with self.assertRaises(ValueError):expand(['VT_FLAGS_SPARSE 512 '+flags])
        before=state();tracker=ThreadLifetimes();tracker.observe(before)
        lost=copy.deepcopy(before);t=lost['threads']['threads'][0];t['flags']=t['flags'][:7]+'-'+t['flags'][8:]
        with self.assertRaises(ValueError):tracker.observe(lost)

if __name__=='__main__':unittest.main()
