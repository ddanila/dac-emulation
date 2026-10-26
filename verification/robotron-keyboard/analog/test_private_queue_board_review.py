import tempfile
import unittest
from pathlib import Path
from private_queue_board_review import inventory, HERE


def snapshots():
    shots=[];current=[]
    for line in (HERE/'reports/private-hdl-queue/corrupt.stdout').read_text().splitlines():
        if line.startswith('VQ_BEGIN'):current=[line]
        elif line.startswith('VQ_') and current:
            current.append(line)
            if line.startswith('VQ_END'):shots.append('\n'.join(current)+'\n');current=[]
    return shots[:3]


class BoardQueueReviewTests(unittest.TestCase):
    def read(self,text,corrupt=False):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';path.write_text(text)
            return inventory(path,corrupt=corrupt)

    def positive(self):
        before,_,_=snapshots()
        return ''.join(f'VQ_BRIDGE {i} {phase} 0.000005\nVQ_STAGE before\n'+before+
                       'VQ_STAGE repeat\n'+before+'VQ_STABLE equal=1\n'
                       for i,phase in enumerate(('before-step','after-step')))

    def test_positive_and_unexercised_fault_are_distinct(self):
        result=self.read(self.positive())
        self.assertEqual(result['boundaries'],2)
        self.assertGreater(result['queuedEventObservations'],0)
        self.assertIsNone(self.read(self.positive(),corrupt=True)['fault'])

    def test_missing_snapshot_and_changed_step_order_rejected(self):
        text=self.positive()
        for bad in (text.replace('VQ_STAGE repeat','VQ_STAGE restored',1),
                    text.replace('VQ_BRIDGE 1 after-step','VQ_BRIDGE 1 before-step',1),
                    text.replace('VQ_STABLE equal=1','VQ_STABLE equal=0',1),
                    text+'VQ_BEGIN 1 0 1 0\n'):
            with self.assertRaises(ValueError):self.read(bad)

    def test_actual_time_mutation_must_be_visible_and_restored(self):
        before,changed,restored=snapshots()
        def text(middle):
            return ('VQ_BRIDGE 0 before-step 0.000005\nVQ_STAGE before\n'+before+
                    'VQ_STAGE changed\n'+middle+'VQ_STAGE restored\n'+restored+
                    'VQ_FAULT detected=1 restored=1\n')
        self.assertIsNotNone(self.read(text(changed),corrupt=True)['fault'])
        with self.assertRaises(ValueError):self.read(text(before),corrupt=True)
        with self.assertRaises(ValueError):self.read(text(changed),corrupt=False)
        with self.assertRaises(ValueError):self.read(text(changed).replace('0.000005','0.000001'),corrupt=True)


if __name__=='__main__':unittest.main()
