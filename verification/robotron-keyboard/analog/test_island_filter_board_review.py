import copy,unittest
from unittest.mock import patch
from island_filter_board_review import bundle,inventory,FAULTS,FilterLifetimes
from test_island_board_review import shot as island_shot
from test_output_callback_board_review import CONTRACT
from test_private_sync_family_board_review import IDENTITIES


def shot(kind='saved',phase=2,events=False,mutation=None):
    tick='0' if phase==1 else '5000000';field=FAULTS.get(mutation);payload=[f'VIF_BEGIN 1 {tick}']
    for index in (2,3):
        selected=index==2
        init=int(phase==1)^int(selected and field==0)
        driven='066' if selected and field==1 else '177' if selected and field==6 else '166'
        propagate=int(selected and field==4)
        payload += [f'VIF_PORT 1 {index} 0x400{index-1}',f'VIF_WIRE {init}',f'VIF_BASE {propagate} 0x0 0 -',
                    f'VIF_VECTOR driven 1 {driven}','VIF_VECTOR forced 0 -']
    payload+=['VIF_END 2']
    return island_shot(kind,phase,events)[:-1]+payload+['VA_END']


def boundary(index,kind='saved',phase=2,events=False,fault=None):
    before=shot(kind,phase,events)
    lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if phase==1 else ' 0.000006'),'VB_STAGE before',*before]
    if fault:return lines+['VB_STAGE changed',*shot(kind,phase,events,fault),'VB_STAGE restored',*before,f'VB_FILTER_FAULT field={FAULTS[fault]} changed=1 restored=1']
    return lines+['VB_STAGE repeat',*before,'VB_STABLE equal=1']


class IslandFilterBoardReview(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('island_filter_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=CONTRACT)

    def test_initialization_and_restored_faults(self):
        initial=boundary(0,'startup',1,True)
        r=self.review(initial+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared'))
        self.assertEqual(r['uniqueIslandFilters'],2);self.assertEqual(r['initializingFilterObservations'],2)
        for name in FAULTS:
            lines=initial+boundary(1,fault=name) if name=='strength' else boundary(0,'startup',1,True,name)
            self.assertIsNotNone(self.review(lines,name)['fault'])

    def test_wrong_binding_missing_referent_and_width(self):
        state=bundle(shot(),IDENTITIES)
        for what in ('pointer','missing','width','mask'):
            bad=copy.deepcopy(state);p=bad['filters']['ports'][0]
            if what=='pointer':p['pointer']+=1
            elif what=='missing':bad['filters']['ports'].pop()
            elif what=='width':p['vectors']['forced']['size']=2
            else:p['mask']={'size':1,'bits':'1'}
            with self.assertRaises(ValueError):FilterLifetimes().observe(bad)

    def test_wrong_time_unrelated_change_and_restore(self):
        with self.assertRaises(ValueError):bundle(island_shot(),IDENTITIES)
        original=boundary(0,'startup',1,True,'init')
        for bad in [[l.replace('restored=1','restored=0') for l in original],
                    [l.replace('VIF_BEGIN 1 0','VIF_BEGIN 1 1') for l in original]]:
            with self.assertRaises(ValueError):self.review(bad,'init')
        bad=original.copy();a=bad.index('VB_STAGE changed');b=bad.index('VB_STAGE restored')
        bad[a:b]=[l.replace('VW_LINK 1 101','VW_LINK 1 103') for l in bad[a:b]]
        with self.assertRaises(ValueError):self.review(bad,'init')

if __name__=='__main__':unittest.main()
