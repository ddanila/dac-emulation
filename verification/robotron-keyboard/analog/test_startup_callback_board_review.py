import unittest
from unittest.mock import patch
from startup_callback_board_review import bundle,inventory
from test_output_callback_board_review import shot as output_shot,CONTRACT
from test_private_sync_family_board_review import IDENTITIES

def shot(kind='saved',phase=2,identity=1):
    return output_shot(kind)[:-1]+[f'VS_START {phase} {identity} {identity if phase==1 else 0}','VA_END']

def boundary(index,kind='saved',phase=2,fault=None,identity=1):
    s=shot(kind,phase,identity)
    lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if kind=='startup' else ' 0.000006'),'VB_STAGE before',*s]
    if fault is not None:return lines+['VB_STAGE restored',*s,f'VB_START_FAULT field={fault} rejected=1 restored=1']
    return lines+['VB_STAGE repeat',*s,'VB_STABLE equal=1']

class StartupCallbackBoard(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('startup_callback_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=CONTRACT)

    def test_active_to_destroyed_and_early_faults(self):
        lines=boundary(0,'startup',1)+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')
        r=self.review(lines);self.assertEqual(r['activeStartupObservations'],1);self.assertEqual(r['destroyedStartupObservations'],3)
        for field,name in enumerate(('user','function','time','link')):
            self.assertEqual(self.review(boundary(0,'startup',1,field),name)['fault']['index'],0)

    def test_missing_rebinding_regression_or_unrestored_fault(self):
        for original,new in [('VS_START 2 1 0','VS_START 2 1 1'),('VS_START 2 1 0','VS_START 1 1 0'),('VS_START 2 1 0','VS_START 2 0 0')]:
            with self.assertRaises(ValueError):bundle([l.replace(original,new) for l in shot()],IDENTITIES)
        with self.assertRaises(ValueError):bundle(output_shot(),IDENTITIES)
        for lines in [boundary(0,'startup',1)+boundary(1,identity=2),
                      boundary(0,'startup',1)+boundary(1)+boundary(2,'startup',1)+boundary(3,'cleared'),
                      boundary(0)+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')]:
            with self.assertRaises(ValueError):self.review(lines)
        lines=boundary(0,'startup',1,0)
        with self.assertRaises(ValueError):self.review([l.replace('restored=1','restored=0') for l in lines],'user')
        with self.assertRaises(ValueError):self.review(lines,'time')

if __name__=='__main__':unittest.main()
