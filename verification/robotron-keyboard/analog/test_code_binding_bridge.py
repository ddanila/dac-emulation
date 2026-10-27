import unittest
from build_code_binding_bridge import code_header,HERE

class CodeBindingBridge(unittest.TestCase):
    def test_all_layers_and_restore_before_verdict(self):
        header=code_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        restore=header.index('robotron_code_fault(ctx,code_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=changed &&',restore))
        self.assertIn('code-null-corrupt',header);self.assertIn('code-foreign-corrupt',header)
        self.assertIn('code_field>=0 && robotron_start_phase==1',header)
        with self.assertRaises(ValueError):code_header('')

if __name__=='__main__':unittest.main()
