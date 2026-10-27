import unittest
from build_scope_bridge import scope_header, HERE


class ScopeBridge(unittest.TestCase):
    def test_all_layers_and_fault_restoration(self):
        header = scope_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)', header)
        restore = header.index('robotron_scope_fault(ctx)!=1)exit(3)')
        self.assertLess(restore, header.index('int detected=changed &&', restore))
        self.assertIn('scope-startup-corrupt', header)
        self.assertIn('scope-late-corrupt', header)
        self.assertIn('scope_late && info->vtime>=5e-6', header)
        with self.assertRaises(ValueError):
            scope_header('')


if __name__ == '__main__':
    unittest.main()
