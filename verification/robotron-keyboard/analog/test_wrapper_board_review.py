import unittest
from unittest.mock import patch
from wrapper_board_review import bundle,inventory
from test_display_stop_bridge import stopped
from test_display_board_review import state
from test_private_sync_family_board_review import IDENTITIES


def shot(kind='saved',delete=0):
    if kind=='saved':s=stopped();frame=[f'VE_FRAME 0 77 1 {delete}']
    else:
        s=state(False)
        if kind=='startup':
            start=next(i for i,l in enumerate(s) if l.startswith('VF_BEGIN '));end=s.index('VF_END',start)
            s[start:end+1]=['VF_BEGIN 1 0 0 0','VF_END']
            s=[l.replace('VD_BEGIN 1 2 2 0','VD_BEGIN 1 0 0 0') for l in s];frame=[]
        else:
            s=[l.replace('VF_CB 1 1 0 9','VF_CB 3 1 0 6').replace('VF_CODE 1 ','VF_CODE 3 ') for l in s]
            frame=[f'VE_FRAME 0 88 3 {delete}']
        s=s[:-1]+['VR_BEGIN 1 0 0','VR_END','VA_END']
    return s[:-1]+[f'VE_BEGIN 1 {len(frame)}',*frame,'VE_END','VA_END']


def boundary(index,kind='saved',fault=None):
    s=shot(kind);lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if kind=='startup' else ' 0.000006'),'VB_STAGE before',*s]
    if fault=='wrapper':lines+=['VB_STAGE changed',*shot(kind,1)]
    if fault:
        markers={'wrapper':'VB_WRAPPER_FAULT detected=1 restored=1','stop':'VB_STOP_FAULT rejected=1 restored=1','display':'VB_FAULT payload_unchanged=1 rejected=1 restored=1'}
        return lines+['VB_STAGE restored',*s,markers[fault]]
    return lines+['VB_STAGE repeat',*s,'VB_STABLE equal=1']


class WrapperBoardTests(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('wrapper_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault)

    def test_combined_roots_and_three_independent_faults(self):
        lines=boundary(0,'startup')+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')
        result=self.review(lines);self.assertEqual(result['uniqueExecutingEvents'],2)
        self.assertEqual(result['emptyFrameObservations'],1)
        for fault in ('wrapper','stop','display'):
            self.assertIsNotNone(self.review(boundary(0,'startup')+boundary(1,fault=fault),fault)['fault'])

    def test_wrong_callback_frame_or_stop_link_rejected(self):
        good=shot()
        for before,after in [('VE_FRAME 0 77 1 0','VE_FRAME 0 77 2 0'),('VR_BEGIN 1 1 1','VR_BEGIN 1 1 2'),('VE_BEGIN 1 1','VE_BEGIN 1 0')]:
            with self.assertRaises(ValueError):bundle([l.replace(before,after) for l in good],IDENTITIES)
        with self.assertRaises(ValueError):bundle([l for l in good if l!='VE_FRAME 0 77 1 0'],IDENTITIES)

    def test_wrong_mutation_or_missing_restoration_rejected(self):
        good=boundary(0,'startup')+boundary(1,fault='wrapper')
        for before,after in [('VE_FRAME 0 77 1 1','VE_FRAME 0 77 1 0'),('restored=1','restored=0'),('detected=1','detected=0')]:
            with self.assertRaises(ValueError):self.review([l.replace(before,after) for l in good],'wrapper')
        with self.assertRaises(ValueError):self.review(good[:-1],'wrapper')
        with self.assertRaises(ValueError):self.review(good,'stop')
        lines=boundary(0,'startup')+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')
        with self.assertRaises(ValueError):self.review([l.replace('VE_FRAME 0 88 3 0','VE_FRAME 0 77 3 0') for l in lines])


if __name__=='__main__':unittest.main()
