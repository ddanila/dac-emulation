import copy,unittest
from unittest.mock import patch
from island_board_review import bundle,inventory,FAULTS,IslandLifetimes
from test_primitive_board_review import shot as primitive_shot
from test_output_callback_board_review import CONTRACT
from test_private_sync_family_board_review import IDENTITIES


def shot(kind='saved',phase=2,events=False,mutation=None):
    tick='0' if phase==1 else '5000000';field=FAULTS.get(mutation)
    flag=int(events)^(field==0)
    inp='166' if field==1 else '077' if field==3 else '066'
    out='066' if field==2 else '166'
    state=0 if field==4 else 1
    side=1 if field==5 else 0
    payload=[f'VI_BEGIN 1 {tick}',f'VI_ISLAND 1 0x1000 {flag} 1 1 3',
             'VI_PORT 1 0x2000 0x3000 0x0',f'VI_VECTOR in 1 {inp}','VI_VECTOR out 0 -','VI_VECTOR scratch 0 -',
             'VI_PORT 2 0x2001 0x3001 0x4001','VI_VECTOR in 1 166',f'VI_VECTOR out 1 {out}','VI_VECTOR scratch 0 -',
             'VI_PORT 3 0x2002 0x3002 0x4002','VI_VECTOR in 1 200','VI_VECTOR out 1 166','VI_VECTOR scratch 0 -',
             f'VI_BRANCH 1 0 2 3 1 {side} 1 1',f'VI_TRAN 0x2000 0 0 0 1 0 {state}','VI_END 1',f'VIQ_BEGIN 1 {tick}']
    if events and field!=6:payload+=['VIQ_EVENT 0 active 0 20 1 0 0x1000']
    payload+=[f'VIQ_END {int(events and field!=6)} {2+int(field==6)}']
    return primitive_shot(kind,phase,events)[:-1]+payload+['VA_END']


def boundary(index,kind='saved',phase=2,events=False,fault=None):
    before=shot(kind,phase,events)
    lines=[f'VB_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+(' 0' if phase==1 else ' 0.000006'),'VB_STAGE before',*before]
    if fault:
        return lines+['VB_STAGE changed',*shot(kind,phase,events,fault),'VB_STAGE restored',*before,f'VB_ISLAND_FAULT field={FAULTS[fault]} changed=1 restored=1']
    return lines+['VB_STAGE repeat',*before,'VB_STABLE equal=1']


class IslandBoardReview(unittest.TestCase):
    def review(self,lines,fault=None):
        with patch('island_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,fault_type=fault,contract=CONTRACT)

    def test_queued_idle_and_all_faults(self):
        initial=boundary(0,'startup',1,True)
        result=self.review(initial+boundary(1)+boundary(2,'cleared')+boundary(3,'cleared'))
        self.assertEqual(result['queuedIslandObservations'],1)
        self.assertEqual(result['idleIslandObservations'],3)
        for name in FAULTS:
            lines=initial+boundary(1,fault=name) if name=='output' else boundary(0,'startup',1,True,name)
            self.assertIsNotNone(self.review(lines,name)['fault'])

    def test_binding_flag_and_lifetime_rejected(self):
        before=bundle(shot('startup',1,True),IDENTITIES)
        for edit in ('key','flag','delete'):
            bad=copy.deepcopy(before)
            if edit=='flag':bad['islands']['islands'][0]['flag']=0
            else:bad['islandQueue']['events'][0][edit]^=1
            with self.assertRaises(ValueError):IslandLifetimes().observe(bad)
        tracker=IslandLifetimes();tracker.observe(before);tracker.observe(bundle(shot(),IDENTITIES))
        with self.assertRaises(ValueError):tracker.observe(before)
        before['islandQueue']['events'][0]['wrapper']+=1
        tracker.observe(before)

    def test_missing_state_and_fault_restoration_rejected(self):
        with self.assertRaises(ValueError):bundle(primitive_shot(),IDENTITIES)
        original=boundary(0,'startup',1,True,'queue')
        for bad in [[l.replace('restored=1','restored=0') for l in original],
                    [l.replace('VIQ_END 0 3','VIQ_END 0 2') for l in original],
                    [l.replace('VIQ_BEGIN 1 0','VIQ_BEGIN 1 1') for l in original]]:
            with self.assertRaises(ValueError):self.review(bad,'queue')
        bad=original.copy();a=bad.index('VB_STAGE changed');b=bad.index('VB_STAGE restored')
        bad[a:b]=[l.replace('VW_LINK 1 101','VW_LINK 1 103') for l in bad[a:b]]
        with self.assertRaises(ValueError):self.review(bad,'queue')

if __name__=='__main__':unittest.main()
