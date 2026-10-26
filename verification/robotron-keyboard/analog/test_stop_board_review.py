import unittest
from unittest.mock import patch
from stop_board_review import inventory
from test_display_board_review import state
from test_display_stop_bridge import stopped
from test_private_sync_family_board_review import IDENTITIES


def boundary(index,saved=True,negative=False):
    if saved:s=stopped()
    else:
        s=[l.replace('VF_CB 1 1 0 9','VF_CB 1 1 0 6') for l in state(False)]
        s=s[:-1]+['VR_BEGIN 1 0 0','VR_END','VA_END']
    return [f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+' 0.000006',
            'VB_STAGE before',*s,'VB_STAGE '+('restored' if negative else 'repeat'),*s,
            'VB_STOP_FAULT rejected=1 restored=1' if negative else 'VB_STABLE equal=1']


class StopBoardTests(unittest.TestCase):
    def review(self,lines,negative=False):
        with patch('stop_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,corrupt=negative)

    def test_saved_and_cleared_relationships_and_restored_invalid_handle(self):
        result=self.review(boundary(0,False)+boundary(1))
        self.assertEqual(result['savedStopObservations'],1)
        self.assertEqual(result['clearedStopObservations'],1)
        self.assertIsNotNone(self.review(boundary(0,False)+boundary(1,negative=True),True)['fault'])

    def test_missing_relationship_bad_pointer_and_false_fault_rejected(self):
        valid=boundary(0,False)+boundary(1,negative=True)
        cases=[[l.replace('VR_BEGIN 1 1 1','VR_BEGIN 1 1 2') for l in valid],
               [l.replace('rejected=1','rejected=0') for l in valid],
               [l.replace('restored=1','restored=0') for l in valid],
               valid[:-1],valid+['VR_BEGIN 1 0 0']]
        for lines in cases:
            with self.assertRaises(ValueError):self.review(lines,True)
        with self.assertRaises(ValueError):self.review(boundary(0)+boundary(1))


if __name__=='__main__':unittest.main()
