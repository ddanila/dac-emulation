import unittest
from build_assignment_bridge import assignment_header,HERE

class AssignmentBridge(unittest.TestCase):
    def test_combined_snapshot_and_restore_before_fault_verdict(self):
        header=assignment_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for function in ('robotron_ports_inventory','robotron_output_inventory','robotron_start_inventory','robotron_assignment_inventory'):
            self.assertIn(function+'(f, ctx)',header)
        restore=header.index('robotron_assignment_fault(ctx,assign_kind,assign_field)!=1) exit(3)')
        self.assertLess(restore,header.index('int detected=changed &&'))
        for mode in ('v4-value','v4-target','v4-width','v8-value','v8-target','v8-strength'):
            self.assertIn('assignment-'+mode+'-corrupt',header)
        with self.assertRaises(ValueError):assignment_header('')

if __name__=='__main__':unittest.main()
