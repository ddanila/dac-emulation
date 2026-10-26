import unittest
from unittest.mock import patch
from port_board_review import bundle,inventory,port_contract
from test_wrapper_board_review import shot as wrapper_shot
from test_private_sync_family_board_review import IDENTITIES

CONTRACT=[{'index':0,'direction':1,'bits':8,'position':0,'name':'top.input'}]


def shot(kind='saved',value=0):
    base=wrapper_shot(kind)
    return base[:-1]+['VP_BEGIN 1 1 0 0','VP_CONTEXT 0x0p+0 0x1p-40 1 0 0',f'VP_PORT 0 1 8 0 1 {value} 0 - - '+b'top.input'.hex(),'VP_END','VA_END']


def boundary(index,kind='saved',fault=None):
    s=shot(kind);lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if kind=='startup' else ' 0.000006'),'VB_STAGE before',*s]
    if fault=='value':lines+=['VB_STAGE changed',*shot(kind,1)]
    if fault:return lines+['VB_STAGE restored',*s,f'VB_PORT_FAULT kind=port-{fault}-corrupt detected=1 restored=1']
    return lines+['VB_STAGE repeat',*s,'VB_STABLE equal=1']


class PortBoardTests(unittest.TestCase):
    def review(self,lines,fault=None,contract=CONTRACT):
        with patch('port_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=contract)

    def test_interface_binding_and_three_port_faults(self):
        lines=boundary(0,'startup')+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared')
        self.assertEqual(self.review(lines)['ports'],CONTRACT)
        for kind in ('handle','context','value'):
            self.assertIsNotNone(self.review(boundary(0,'startup')+boundary(1,fault=kind),kind)['fault'])
        with self.assertRaises(ValueError):self.review(lines,contract=[dict(CONTRACT[0],name='top.other')])

    def test_wrong_values_missing_identity_and_false_fault_rejected(self):
        lines=boundary(0,'startup')+boundary(1,fault='value')
        for before,after in [('0 1 8 0 1 1 0','0 1 8 0 1 0 0'),('restored=1','restored=0'),('- -','0 0')]:
            with self.assertRaises(ValueError):self.review([l.replace(before,after) for l in lines],'value')
        with self.assertRaises(ValueError):bundle([l for l in shot() if not l.startswith('VP_PORT')],IDENTITIES)
        with self.assertRaises(ValueError):self.review(lines[:-1],'value')

    def test_compiled_contract_groups_directions_and_preserves_port_order(self):
        source='''S_top .scope module, "top" "top" 2 1;
    .port_info 0 /OUTPUT 2 "o";
    .port_info 1 /INPUT 8 "input";
    .port_info 2 /INPUT 1 "clock";
    .port_info 3 /INOUT 4 "bus";
S_child .scope module, "child" "child" 2 10, S_top;
    .port_info 0 /OUTPUT 1 "ignored";
'''
        result=port_contract(source)
        self.assertEqual([p['name'] for p in result],['top.input','top.clock','top.o','top.bus'])
        self.assertEqual([p['position'] for p in result],[0,8,0,0])
        for bad in (source+source,source.replace('.port_info 2 ','.port_info 7 '),source.replace('/INPUT','/UNKNOWN')):
            with self.assertRaises(ValueError):port_contract(bad)


if __name__=='__main__':unittest.main()
