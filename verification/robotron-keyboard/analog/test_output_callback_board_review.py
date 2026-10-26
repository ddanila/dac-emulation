import unittest
from unittest.mock import patch
from output_callback_board_review import bundle,inventory
from test_wrapper_board_review import shot as wrapper_shot
from test_private_sync_family_board_review import IDENTITIES

CONTRACT=[{'index':i,'direction':i+1,'bits':1,'position':0,'name':name}
          for i,name in enumerate(('top.in','top.out','top.io'))]


def shot(kind='saved',first=101):
    ports=['VP_BEGIN 1 1 1 1','VP_CONTEXT 0x0p+0 0x1p-40 0 0 0']
    for p in CONTRACT:
        words='- -' if p['direction']==1 else '0 0'
        ports.append(f"VP_PORT {p['index']} {p['direction']} 1 0 0 0 0 {words} "+p['name'].encode().hex())
    return wrapper_shot(kind)[:-1]+ports+['VP_END','VW_BEGIN 1 2',f'VW_LINK 1 {first}','VW_LINK 2 102','VW_END','VA_END']


def boundary(index,kind='saved',fault=None,first=101):
    s=shot(kind,first);lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if kind=='startup' else ' 0.000006'),'VB_STAGE before',*s]
    if fault is not None:return lines+['VB_STAGE restored',*s,f'VB_OUTPUT_FAULT field={fault} rejected=1 restored=1']
    return lines+['VB_STAGE repeat',*s,'VB_STABLE equal=1']


class OutputCallbackBoard(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('output_callback_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=CONTRACT)

    def test_registered_outputs_and_all_restored_faults(self):
        lines=boundary(0,'startup')+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')
        self.assertEqual(self.review(lines)['outputCallbacks'],[{'port':1,'callbackId':101},{'port':2,'callbackId':102}])
        for field,name in enumerate(('user','object','function','link')):
            self.assertIsNotNone(self.review(boundary(0,'startup')+boundary(1,fault=field),name)['fault'])

    def test_missing_alias_or_changed_lifetime_rejected(self):
        original=shot()
        for old,new in [('VW_LINK 1 101','VW_LINK 0 101'),('VW_LINK 1 101','VW_LINK 1 102'),('VW_BEGIN 1 2','VW_BEGIN 1 3')]:
            with self.assertRaises(ValueError):bundle([l.replace(old,new) for l in original],IDENTITIES)
        with self.assertRaises(ValueError):bundle([l for l in original if not l.startswith('VW_LINK 1')],IDENTITIES)
        with self.assertRaises(ValueError):self.review(boundary(0,'startup')+boundary(1,first=103))
        lines=boundary(0,'startup')+boundary(1,fault=0)
        with self.assertRaises(ValueError):self.review([l.replace('restored=1','restored=0') for l in lines],'user')
        with self.assertRaises(ValueError):self.review(lines,'object')


if __name__=='__main__':unittest.main()
