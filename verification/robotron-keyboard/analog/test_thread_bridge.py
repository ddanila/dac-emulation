import unittest
from build_thread_bridge import thread_header,HERE

class ThreadBridge(unittest.TestCase):
    def test_prior_observers_and_restoration_before_verdict(self):
        header=thread_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        restore=header.index('robotron_thread_fault(ctx,thread_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=changed &&',restore))
        self.assertIn('thread_field==2 ? info->vtime>=5e-6',header)
        for mode in ('schedule','flag','word','pc','wait','queue'):
            self.assertIn('thread-'+mode+'-corrupt',header)
        with self.assertRaises(ValueError):thread_header('')

if __name__=='__main__':unittest.main()
