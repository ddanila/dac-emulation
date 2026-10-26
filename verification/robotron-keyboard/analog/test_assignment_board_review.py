import unittest
from unittest.mock import patch
from assignment_board_review import bundle,inventory,FAULTS
from test_startup_callback_board_review import shot as startup_shot
from test_output_callback_board_review import CONTRACT
from test_private_sync_family_board_review import IDENTITIES

def shot(kind='saved',phase=2,events=False,mutation=None):
    payload=['VAP_BEGIN 1 '+('0' if phase==1 else '5000000')]
    if events:
        a=['VAP_EVENT','0','active','0','1','4','0x1000','0','0','0','4','0011']
        b=['VAP_EVENT','0','active','1','2','8','0x2000','0','0','0','1','166']
        if mutation:
            k,f=FAULTS[mutation];target=a if k==4 else b
            if f==0:target[11]='1011' if k==4 else '066'
            elif f==1:target[7]='1'
            elif k==4:target[9]='1'
            else:target[11]='335'
        payload+=[' '.join(a),' '.join(b),'VAP_END 1 1 2']
    else:payload+=['VAP_END 0 0 0']
    return startup_shot(kind,phase)[:-1]+payload+['VA_END']

def boundary(index,kind='saved',phase=2,events=False,fault=None):
    before=shot(kind,phase,events)
    lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if phase==1 else ' 0.000006'),'VB_STAGE before',*before]
    if fault:
        k,f=FAULTS[fault]
        return lines+['VB_STAGE changed',*shot(kind,phase,events,fault),'VB_STAGE restored',*before,f'VB_ASSIGN_FAULT kind={k} field={f} changed=1 restored=1']
    return lines+['VB_STAGE repeat',*before,'VB_STABLE equal=1']

class AssignmentBoardReview(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('assignment_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=CONTRACT)

    def test_payload_consumption_and_all_restored_faults(self):
        lines=boundary(0,'startup',1,True)+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')
        r=self.review(lines);self.assertEqual(r['uniqueAssignments'],2);self.assertEqual(r['emptyAssignmentBoundaries'],3)
        for name in FAULTS:self.assertEqual(self.review(boundary(0,'startup',1,True,name),name)['fault']['index'],0)

    def test_wrong_fault_rebinding_and_missing_payload_rejected(self):
        with self.assertRaises(ValueError):bundle(startup_shot(),IDENTITIES)
        with self.assertRaises(ValueError):bundle([l.replace('VAP_BEGIN 1 5000000','VAP_BEGIN 1 5000001') for l in shot()],IDENTITIES)
        for lines in [boundary(0,'startup',1,True)+boundary(1)+boundary(2,'cleared',2,True)+boundary(3,'cleared'),
                      boundary(0,'startup',1,True)+boundary(1,'saved',2,True)+boundary(2,'cleared',2,True)+boundary(3,'cleared',2,True)]:
            with self.assertRaises(ValueError):self.review(lines)
        original=boundary(0,'startup',1,True,'v4-value')
        for bad in [[l.replace('restored=1','restored=0') for l in original],
                    [l.replace('VAP_END 1 1 2','VAP_END 1 0 2') for l in original],
                    [l.replace(' 4 1011',' 4 0011') for l in original]]:
            with self.assertRaises(ValueError):self.review(bad,'v4-value')
        with self.assertRaises(ValueError):self.review(original,'v8-value')
        bad=original.copy();at=bad.index('VB_STAGE changed');end=bad.index('VB_STAGE restored')
        bad[at:end]=[l.replace('VW_LINK 1 101','VW_LINK 1 103') for l in bad[at:end]]
        with self.assertRaises(ValueError):self.review(bad,'v4-value')

if __name__=='__main__':unittest.main()
