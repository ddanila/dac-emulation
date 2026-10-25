from pathlib import Path
import tempfile
import unittest
from history_state_review import snapshots


def snapshot(phase,pending=False,published=False):
    return (f'H_BEGIN {phase} 1e-6\nH_SCHED 0x0p+0 0x0p+0 0x0p+0 0 {int(pending)}\n'
            'H_QUEUE 0 0x0p+0 0 0 1\nH_ARRAY 0 0 1 0:1\nH_ARRAY 0 1 1 0:1\n'
            f'H_ARRAY 1 0 1 {int(published)}:1\nH_ARRAY 1 1 1 0:1\n'
            +('H_PENDING 1 1:1\n' if pending else 'H_PENDING 0\n')+'H_END\n')


class HistoryTests(unittest.TestCase):
    def test_complete_and_damaged_history(self):
        text=''.join(snapshot(p) for p in ('callback-entry','event-after','run-entry','advance-before','advance-after'))
        text+=snapshot('output-before',True)+snapshot('output-after',published=True)+'H_REJECT 1e-6 equal=1\n'
        mutations={'none':text,'missing_array':text.replace('H_ARRAY 0 1 1 0:1\n','',1),
                   'wrong_publish':text.replace('H_ARRAY 1 0 1 1:1','H_ARRAY 1 0 1 0:1'),
                   'corruption':text.replace('equal=1','equal=0'),
                   'truncated':text+'H_BEGIN run-entry 2e-6\n',
                   'missing_advance':text.replace(snapshot('advance-after'),''),
                   'nonfinite_rejection':text.replace('H_REJECT 1e-6','H_REJECT nan'),
                   'missing_queue':text.replace('H_QUEUE 0 0x0p+0 0 0 1\n','',1)}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log'
            for name,value in mutations.items():
                with self.subTest(name=name):
                    p.write_text(value);stats={}
                    if name=='none':
                        self.assertEqual(len(list(snapshots(p,stats))),7)
                        self.assertEqual(stats['rejections'],1)
                    else:
                        with self.assertRaises(ValueError):list(snapshots(p,stats))
            p.write_text(snapshot('run-entry')+'H_REJECT 1e-6 equal=0\n')
            stats={};list(snapshots(p,stats,corrupt=True));self.assertEqual(stats['corruptionsDetected'],1)

if __name__=='__main__':unittest.main()
