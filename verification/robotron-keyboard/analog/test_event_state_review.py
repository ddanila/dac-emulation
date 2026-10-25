from pathlib import Path
import tempfile
import unittest
from event_state_review import scheduling

class EventStateTests(unittest.TestCase):
    def test_pending_events_and_damaged_records(self):
        start=1e-6;delay=1e-9;end=start+delay
        text=(f'H_BEGIN output-after {start:.17g}\nH_ARRAY 1 0 1 1:0\n'
              f'E_SUM 0x0p+0 {end.hex()} 0 1 0\n'
              f'E_PORT 1 0 2 1 {delay.hex()} 1 1 0 0\nH_END\n'
              f'H_BEGIN callback-entry {start+delay/2:.17g}\nH_ARRAY 1 0 1 1:0\n'
              f'E_SUM 0x0p+0 {end.hex()} 0 1 0\n'
              f'E_PORT 1 0 2 1 {delay.hex()} 0 0 0 1\n'
              f'E_ITEM 2 0 {end.hex()} {start.hex()} 0 0x0p+0 1 0\nH_END\n')
        mutations={'none':text,'missing_event':text.replace('0 0 0 1\n','0 0 0 2\n'),
                   'reordered_event':text.replace('E_ITEM 2 0','E_ITEM 2 1'),
                   'wrong_publication':text.replace('1 1 0 0\nH_END','1 0 0 0\nH_END'),
                   'unassigned_read':text.replace('H_BEGIN output-after','H_BEGIN output-before'),
                   'truncated':text.rsplit('H_END',1)[0],
                   'missing_port':text.replace('H_ARRAY 1 0 1 1:0','H_ARRAY 1 0 2 1:0 0:0')}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log'
            for name,value in mutations.items():
                with self.subTest(name=name):
                    p.write_text(value)
                    if name=='none':
                        result=scheduling(p);self.assertEqual(result['publicationsWitnessedInPendingQueue'],1)
                        self.assertEqual(result['maximumObservedPendingEvents'],1)
                    else:
                        with self.assertRaises(ValueError):scheduling(p)

if __name__=='__main__':unittest.main()
