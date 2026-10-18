import unittest
from boot_cosim import capture_command, check_capture_extent


class BoardCaptureTests(unittest.TestCase):
    def test_startup_cannot_be_replaced_by_a_tail(self):
        check_capture_extent(0,.154,[0,.154],10)
        with self.assertRaises(ValueError):
            check_capture_extent(.124,.154,[0,.154],10)
        self.assertEqual(capture_command(10,[0,.154]),'tran 10n 0.154 0')

    def test_tail_start_has_only_one_step_allowance(self):
        check_capture_extent(.124000005,.154,[.124,.154],10)
        for first,last in [(0,.154),(.124001,.154),(.124,.153),(.124,.155),(None,.154)]:
            with self.assertRaises(ValueError):
                check_capture_extent(first,last,[.124,.154],10)
        self.assertEqual(capture_command(10,[.124,.154]),'tran 10n 0.154 124m')

    def test_invalid_window_or_step(self):
        for window,step in [([.123,.154],10),([0,float('nan')],10),([.124,.124],10),([0,.154],0)]:
            with self.assertRaises(ValueError):capture_command(step,window)
