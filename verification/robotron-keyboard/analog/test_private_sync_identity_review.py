import unittest
from unittest.mock import patch
from private_sync_identity_review import inventory,snapshot


def shot(sync=0):
    return ['VS_BEGIN 1 5000000 4 2',
            'VS_CALLBACK 1 1 0 9 0 1 1 1 1 1 1 1 1 2 0 5000000 0x0p+0',
            f'VS_CALLBACK 2 0 {sync} 9 0 1 1 1 1 1 1 1 1 2 0 1000 0x0p+0','VS_END']


def boundary(index,negative=False):
    lines=[f'VS_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+' 0.000005','VS_STAGE before',*shot()]
    if negative:return lines+['VS_STAGE changed',*shot(1),'VS_STAGE restored',*shot(),'VS_FAULT detected=1 restored=1']
    return lines+['VS_STAGE repeat',*shot(),'VS_STABLE equal=1']


class SyncIdentityReviewTests(unittest.TestCase):
    def review(self,lines,negative=False):
        with patch('private_sync_identity_review.records',return_value=iter(lines)):
            return inventory(None,corrupt=negative)

    def test_complete_boundaries_and_non_time_fault(self):
        result=self.review(boundary(0)+boundary(1))
        self.assertEqual(result['executingCallbackObservations'],2)
        self.assertTrue(result['functionIdentityEstablished'])
        result=self.review(boundary(0,True),True)
        self.assertEqual(result['fault']['index'],0)

    def test_orphan_missing_changed_and_unrestored_state_rejected(self):
        positive=boundary(0)+boundary(1)
        cases=[positive[:-1],positive[1:],positive+[positive[0]],
               [line.replace('VS_BRIDGE 1','VS_BRIDGE 2') for line in positive],
               [line.replace('VS_STABLE equal=1','VS_STABLE equal=0') for line in positive]]
        for lines in cases:
            with self.assertRaises(ValueError):self.review(lines)
        negative=boundary(0,True)
        for i in (negative.index('VS_STAGE changed')+3,negative.index('VS_STAGE restored')+3):
            bad=negative[:];a=bad[i].split();a[3]='0' if a[3]=='1' else '1';bad[i]=' '.join(a)
            with self.assertRaises(ValueError):self.review(bad,True)

    def test_identity_and_executing_state_cannot_be_inferred(self):
        original=shot();snapshot(original)
        for index in (7,8,9,10,11,12,13):
            bad=original[:];a=bad[1].split();a[index]='1' if a[index]=='0' else '0';bad[1]=' '.join(a)
            with self.assertRaises(ValueError):snapshot(bad)
        bad=original[:];bad[0]='VS_BEGIN 1 5000000 0 2'
        with self.assertRaises(ValueError):snapshot(bad)
        lines=[s.replace('VS_CALLBACK 1 1','VS_CALLBACK 1 0') for s in boundary(0)+boundary(1)]
        with self.assertRaises(ValueError):self.review(lines)


if __name__=='__main__':unittest.main()
