from pathlib import Path
import tempfile
import unittest
from live_cosim_state_review import records
from audit_log import equal


class LiveStateTests(unittest.TestCase):
    def test_complete_inventory_and_rejected_trial(self):
        names=['board.cpu.pc']+['board.rom[%d]'%i for i in range(2048)]
        text='STATE_INVENTORY items=2049\n'+''.join('STATE_OBJECT %s 8\n'%n for n in names)
        text+='STATE_ENTRY 0\n'+''.join('state %s 8 00000000\n'%n for n in names)+'STATE_END\n'
        text+='STATE_REJECT 1e-9 equal=1\nFIRST_FETCH 1 0000 00\nNo. of Data Rows : 2\n'
        for mutation in ('none','missing_word','duplicate','truncated','changed','no_completion'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                modified=text
                if mutation=='missing_word':modified=modified.replace('state board.rom[0] 8 00000000\n','')
                if mutation=='duplicate':modified=modified.replace('STATE_END\n','state board.cpu.pc 8 00000000\nSTATE_END\n')
                if mutation=='truncated':modified=modified.replace('STATE_END\n','')
                if mutation=='changed':modified=modified.replace('equal=1','equal=0')
                if mutation=='no_completion':modified=modified.replace('No. of Data Rows : 2\n','')
                p=Path(tmp)/'log';p.write_text(modified);summary={}
                if mutation=='none':
                    baseline=list(records(p,summary));self.assertEqual(summary['rejections'],1)
                    shifted=Path(tmp)/'shifted'
                    shifted.write_text('FIRST_FETCH 1 0000 00\n'+text.replace('FIRST_FETCH 1 0000 00\n',''))
                    self.assertEqual(baseline,list(records(shifted,{})))
                    self.assertTrue(equal(p,shifted,('FIRST_FETCH ',)))
                    shifted.write_text(shifted.read_text().replace('FIRST_FETCH 1 ','FIRST_FETCH 2 '))
                    self.assertFalse(equal(p,shifted,('FIRST_FETCH ',)))
                    self.assertTrue(summary['firmwareFetched'])
                else:
                    with self.assertRaises(ValueError):list(records(p,summary))

if __name__=='__main__':unittest.main()
