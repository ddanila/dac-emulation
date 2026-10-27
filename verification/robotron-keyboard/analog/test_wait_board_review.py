import copy,unittest
from wait_board_review import WaitLifetimes,changed_wait
from test_thread_board_review import state as thread_state


def state():
    s=thread_state();s['waitEvents']=dict(tick=1000,events=[
        dict(id=1,kind=1,owner=0x500,context=0,hasHead=1,thread=3,head=0x300,referent=0,caches=[],edge=dict(mask=8718,bits='0333')),
        dict(id=2,kind=2,owner=0x600,context=0,hasHead=1,thread=0,head=0,referent=0,caches=[dict(kind=0,size=0,data='-') for _ in range(4)])])
    return s


class WaitBoardReview(unittest.TestCase):
    def test_complete_owner_and_initialized_cache_coverage(self):
        s=state();tracker=WaitLifetimes();tracker.observe(s)
        s['waitEvents']['events'][1]['caches'][0]=dict(kind=1,size=1,data='1')
        tracker.observe(s);r=tracker.result(False)
        self.assertEqual(r['waitEventKinds'],{1:1,2:1})
        self.assertEqual(r['nonemptyWaitHeads'],2)

    def test_missing_owner_layout_and_pointer_change_rejected(self):
        for mode in ('head','owner','missing','automatic'):
            tracker=WaitLifetimes();tracker.observe(state());bad=state()
            if mode=='head':bad['waitEvents']['events'][0].update(thread=0,head=0)
            elif mode=='owner':bad['waitEvents']['events'][0]['owner']+=1
            elif mode=='missing':bad['waitEvents']['events'].pop()
            else:bad['waitEvents']['events'][0]['kind']=11
            with self.assertRaises(ValueError):tracker.observe(bad)

    def test_exact_mutation_and_unrelated_state(self):
        before=state();after=copy.deepcopy(before);after['waitEvents']['events'][0].update(thread=0,head=0)
        changed_wait(before,after,'head')
        after['threads']['threads'][0]['pc']=0
        with self.assertRaises(ValueError):changed_wait(before,after,'head')
        after=copy.deepcopy(before);after['waitEvents']['events'][0]['edge']['mask']^=1
        changed_wait(before,after,'mask')
        after['waitEvents']['events'][0]['edge']['bits']='1333'
        with self.assertRaises(ValueError):changed_wait(before,after,'mask')

if __name__=='__main__':unittest.main()
