import unittest
from unittest.mock import patch
from display_board_review import HERE,bundle,inventory
from test_private_sync_family_board_review import IDENTITIES,shot


def state(pending=True):
    lines=(HERE/'reports/display-association/enabled.stdout').read_text().splitlines()
    starts=[i for i,l in enumerate(lines) if l=='VA_BEGIN'];start=starts[0 if pending else 2]
    source=lines[start:lines.index('VA_END',start)+1]
    v=source.index(next(l for l in source if l.startswith('VD_BEGIN')))
    tail=source[v:-1]
    if pending:
        tail=[l for l in tail if not l.startswith(('VD_INFO 2 ','VD_ITEM 2 ','VJ_LINK 2 '))]
        tail=[l.replace('VD_BEGIN 1 2 0 2','VD_BEGIN 1 2 1 1').replace('VJ_BEGIN 1 2','VJ_BEGIN 1 1').replace('VJ_LINK 1 1','VJ_LINK 1 2') for l in tail]
        callbacks=shot()
    else:
        callbacks=shot()[:3]+['VF_END'];callbacks[0]='VF_BEGIN 1 5000000 4 1'
    return ['VA_BEGIN',*callbacks,*tail,'VA_END']


def boundary(index,pending=True,fault=False):
    s=state(pending)
    result=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+' 0.000006','VB_STAGE before',*s]
    return result+['VB_STAGE '+('restored' if fault else 'repeat'),*s,('VB_FAULT payload_unchanged=1 rejected=1 restored=1' if fault else 'VB_STABLE equal=1')]


class BoardDisplayTests(unittest.TestCase):
    def review(self,lines,negative=False):
        with patch('display_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,corrupt=negative)

    def test_stop_callback_can_coexist_with_linked_display(self):
        self.assertEqual(bundle(state(),IDENTITIES)['links'],{1:2})
        result=self.review(boundary(0)+boundary(1,False))
        self.assertEqual(result['associatedDisplayObservations'],1)
        self.assertEqual(result['releasedDisplayObservations'],1)
        self.assertIsNotNone(self.review(boundary(0,False)+boundary(1,fault=True),True)['fault'])

    def test_link_to_stop_missing_link_unknown_function_and_payload_rejected(self):
        valid=state()
        cases=[[l.replace('VJ_LINK 1 2','VJ_LINK 1 1') for l in valid],
               [l for l in valid if not l.startswith('VJ_LINK')],
               [l for l in valid if not l.startswith('VD_ITEM 1 1 ')],
               [l[:-2]+'21' if l.startswith('VF_CODE 2 ') else l for l in valid]]
        for lines in cases:
            with self.assertRaises(ValueError):bundle(lines,IDENTITIES)

    def test_false_fault_markers_incomplete_boundaries_and_restoration_rejected(self):
        valid=boundary(0,False)+boundary(1,fault=True)
        for before,after in [('rejected=1','rejected=0'),('restored=1','restored=0'),('payload_unchanged=1','payload_unchanged=0'),('VB_BRIDGE 1','VB_BRIDGE 2')]:
            with self.assertRaises(ValueError):self.review([l.replace(before,after) for l in valid],True)
        with self.assertRaises(ValueError):self.review(valid[:-1],True)
        altered=valid[:];i=altered.index('VB_STAGE restored');altered[i+1:]=[l.replace('VD_INFO 1 0','VD_INFO 1 1') for l in altered[i+1:]]
        with self.assertRaises(ValueError):self.review(altered,True)


if __name__=='__main__':unittest.main()
