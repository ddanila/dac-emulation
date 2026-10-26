import unittest
from build_island_bridge import island_header,HERE

class IslandBridge(unittest.TestCase):
    def test_combined_snapshot_and_restore_before_fault_verdict(self):
        header=island_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for function in ('robotron_ports_inventory','robotron_output_inventory','robotron_start_inventory','robotron_assignment_inventory','robotron_primitive_inventory','robotron_island_inventory'):
            self.assertIn(function+'(f, ctx)',header)
        restore=header.index('robotron_island_fault(ctx,island_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=changed &&'))
        for mode in ('flag','input','output','strength','enable','mesh','queue'):
            self.assertIn('island-'+mode+'-corrupt',header)
        with self.assertRaises(ValueError):island_header('')

if __name__=='__main__':unittest.main()
