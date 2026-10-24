import unittest
from live_bridge_time_capture import substitute_vpi


class BridgeSubstitutionTests(unittest.TestCase):
    def test_only_explicit_library_argument_changes(self):
        deck='title\n.model hdl d_cosim simulation="/a/shim.so"\n+ lib_args=["/a/libvvp.so" "/a/ivlng.vpi"]\nV1 a 0 5\n'
        self.assertEqual(substitute_vpi(deck,'/a/ivlng.vpi','/audit/ivlng.vpi'),deck.replace('"/a/ivlng.vpi"','"/audit/ivlng.vpi"'))

    def test_rejects_duplicate_missing_or_wrong_location(self):
        for deck in ('title\n', 'V1 a 0 "/a/ivlng.vpi"\n',
                     '+ lib_args=["/a/libvvp.so" "/a/ivlng.vpi"]\n* "/a/ivlng.vpi"\n'):
            with self.subTest(deck=deck),self.assertRaises(ValueError):
                substitute_vpi(deck,'/a/ivlng.vpi','/audit/ivlng.vpi')


if __name__=='__main__':unittest.main()
