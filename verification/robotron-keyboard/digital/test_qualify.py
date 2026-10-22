import unittest
from qualify import scenarios,fixtures,compare,assess

class QualificationTests(unittest.TestCase):
    def test_every_contact_and_both_reset_boundaries(self):
        cases=scenarios();contacts={(e[2],e[3]) for c in cases if c['id'].startswith('column-') for e in c['events'] if e[1]=='key'}
        self.assertEqual(contacts,{(c,r) for c in range(13) for r in range(8)})
        for case in cases:
            c,v=fixtures(case)
            self.assertIn('DONE',c);self.assertIn('DONE',v)
            for e in case['events']:
                self.assertIn('cycle=='+str(e[0]),c);self.assertIn(str(e[0])+':',v)
        self.assertEqual(len([c for c in cases if c['id'].startswith('reset-')]),2)

    def test_missing_event_and_phase_difference_are_distinct(self):
        a={k:[] for k in ('BIT','EDGE','LED','BUS')};a['BIT']=[['10','1'],['20','0']]
        b=dict(a,BIT=[['12','1'],['22','0']]);r=compare(a,b)['BIT']
        self.assertTrue(r['valuesEquivalent']);self.assertFalse(r['rawCycleEquivalent'])
        self.assertEqual(r['offsetCounts'],{'2':2})
        self.assertFalse(compare(a,dict(b,BIT=b['BIT'][:1]))['BIT']['valuesEquivalent'])
        self.assertFalse(compare(a,dict(b,BIT=[['12','x'],['22','0']]))['BIT']['valuesEquivalent'])

    def test_observation_window_keeps_interior_mismatches(self):
        from review import observation_window
        inside,outside=observation_window({'EDGE':[['0','0'],['99','1'],['100','0']]},100)
        self.assertEqual(inside['EDGE'],[['0','0'],['99','1']])
        self.assertEqual(outside['EDGE'],[['100','0']])

    def test_reset_requires_partial_frame_witness(self):
        case={'events':[[100,'reset']],'cycles':200}
        a={k:[] for k in ('BIT','EDGE','LED','BUS')};a['BIT']=[['80','1'],['120','0']]
        r=assess(case,a,a)
        self.assertTrue(r['resetWitnesses'][0]['c']['partial26BitFrame'])
        self.assertEqual(r['resetWitnesses'][0]['hdl']['postResetBits'],1)
if __name__=='__main__':unittest.main()
