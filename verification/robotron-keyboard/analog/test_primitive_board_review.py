import copy
import unittest
from unittest.mock import patch
from primitive_board_review import bundle,inventory,FAULTS,PrimitiveLifetimes
from test_assignment_board_review import shot as assignment_shot
from test_output_callback_board_review import CONTRACT
from test_private_sync_family_board_review import IDENTITIES


def shot(kind='saved',phase=2,events=False,mutation=None):
    payload=['VPR_BEGIN 1 '+('0' if phase==1 else '5000000')]
    if events:
        a=['VPR_DATA','1','0x1000','0','0','4','0011']
        b=['VPR_DATA','2','0x2000','4','2','2','01']
        if mutation:
            k,f=FAULTS[mutation];target=a if k==1 else b
            if f==0:target[6]='1011' if k==1 else '11'
            elif f==1:target[2]='0x0'
            else:target[3]='5'
        payload+=['VPR_EVENT 0 active 0 10 1 1 0',' '.join(a),
                  'VPR_EVENT 0 active 1 11 2 2 0',' '.join(b),'VPR_END 2 2']
    else:payload+=['VPR_END 0 0']
    return assignment_shot(kind,phase,events)[:-1]+payload+['VA_END']


def boundary(index,kind='saved',phase=2,events=False,fault=None):
    before=shot(kind,phase,events)
    lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if phase==1 else ' 0.000006'),'VB_STAGE before',*before]
    if fault:
        k,f=FAULTS[fault]
        return lines+['VB_STAGE changed',*shot(kind,phase,events,fault),'VB_STAGE restored',*before,f'VB_PRIMITIVE_FAULT kind={k} field={f} changed=1 restored=1']
    return lines+['VB_STAGE repeat',*before,'VB_STABLE equal=1']


class PrimitiveBoardReview(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('primitive_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=CONTRACT)

    def test_consumption_and_restored_faults(self):
        r=self.review(boundary(0,'startup',1,True)+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared'))
        self.assertEqual(r['uniquePrimitives'],2)
        self.assertEqual(r['emptyPrimitiveBoundaries'],3)
        for name in FAULTS:self.assertEqual(self.review(boundary(0,'startup',1,True,name),name)['fault']['index'],0)

    def test_coalescing_and_wrapper_lifetimes(self):
        snapshot=bundle(shot('startup',1,True),IDENTITIES)['primitives']
        tracker=PrimitiveLifetimes();tracker.observe(snapshot)
        changed=copy.deepcopy(snapshot);changed['events'][0]['bits']='1111'
        tracker.observe(changed) # Input coalescing can update an already queued cache.
        tracker.observe(dict(snapshot,events=[]))
        with self.assertRaises(ValueError):tracker.observe(changed)
        for event in changed['events']:event['wrapper']+=20
        tracker.observe(changed)
        changed['events'][0]['target']+=1
        with self.assertRaises(ValueError):tracker.observe(changed)

    def test_missing_state_wrong_fault_and_unrelated_change(self):
        with self.assertRaises(ValueError):bundle(assignment_shot(),IDENTITIES)
        with self.assertRaises(ValueError):bundle([l.replace('VPR_BEGIN 1 5000000','VPR_BEGIN 1 5000001') for l in shot()],IDENTITIES)
        original=boundary(0,'startup',1,True,'not-value')
        with self.assertRaises(ValueError):self.review(original,'part-value')
        for bad in [[l.replace('restored=1','restored=0') for l in original],
                    [l.replace('VPR_END 2 2','VPR_END 1 2') for l in original],
                    [l.replace(' 4 1011',' 4 0011') for l in original]]:
            with self.assertRaises(ValueError):self.review(bad,'not-value')
        bad=original.copy();at=bad.index('VB_STAGE changed');end=bad.index('VB_STAGE restored')
        bad[at:end]=[l.replace('VW_LINK 1 101','VW_LINK 1 103') for l in bad[at:end]]
        with self.assertRaises(ValueError):self.review(bad,'not-value')

if __name__=='__main__':unittest.main()
