import unittest
from scenario_capture import endpoint_ns


class ScenarioCaptureTests(unittest.TestCase):
    def test_full_repeat_endpoint_is_derived_from_cycles_and_reset(self):
        self.assertEqual(endpoint_ns('.tran 25n 1601000000n\n',{'cycles':1600000}),1601000000)
        self.assertEqual(endpoint_ns('.tran 25n 1.601e9n\n',{'cycles':1600000},1601000000),1601000000)

    def test_rejects_shortening_extension_skipped_start_and_halt(self):
        for deck,override in [('.tran 25n 1006000n\n',None),
                              ('.tran 25n 1601000001n\n',None),
                              ('.tran 25n 1601000000n\n',1006000),
                              ('.tran 25n 1601000000n\n',float('nan')),
                              ('.tran 25n 1601000000n 1000000n\n',None),
                              ('.tran 25n 1601000000n\nstop when time = 1m\n',None),
                              ('.tran 25n 1601000000n\n.tran 25n 1601000000n\n',None)]:
            with self.subTest(deck=deck,override=override),self.assertRaises(ValueError):
                endpoint_ns(deck,{'cycles':1600000},override)


if __name__=='__main__':unittest.main()
