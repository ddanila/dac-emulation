import unittest
from build_island_filter_bridge import filter_header,HERE

class IslandFilterBridge(unittest.TestCase):
    def test_combined_snapshot_and_restore_before_fault_verdict(self):
        header=filter_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for function in ('robotron_ports_inventory','robotron_output_inventory','robotron_start_inventory','robotron_assignment_inventory','robotron_primitive_inventory','robotron_island_inventory','robotron_filter_inventory'):
            self.assertIn(function+'(f, ctx)',header)
        restore=header.index('robotron_filter_fault(ctx,filter_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=changed &&'))
        for mode in ('init','driven','propagate','strength'):
            self.assertIn('filter-'+mode+'-corrupt',header)
        with self.assertRaises(ValueError):filter_header('')

if __name__=='__main__':unittest.main()
