import unittest
from build_wait_bridge import wait_header,HERE

class WaitBridge(unittest.TestCase):
    def test_combined_snapshot_and_restore_before_verdict(self):
        header=wait_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        restore=header.index('robotron_wait_fault(ctx,wait_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=changed &&',restore))
        for mode in ('head','mask','history','cache'):
            self.assertIn('wait-'+mode+'-corrupt',header)
        self.assertIn('wait_field==0 || wait_field==3',header)
        with self.assertRaises(ValueError):wait_header('')

if __name__=='__main__':unittest.main()
