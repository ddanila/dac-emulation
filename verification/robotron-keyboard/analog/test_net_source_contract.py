import json
import unittest
from pathlib import Path
from net_source_contract import profile
HERE=Path(__file__).resolve().parent


class NetProfile(unittest.TestCase):
    def text(self):return (HERE/'reports/wait-board/off/io.vvp').read_text()
    def test_retained_profile(self):
        result=profile(self.text())
        self.assertEqual(result,json.loads((HERE/'reports/net-source-contract/assessment.json').read_text())['compiled'])
        self.assertTrue(result['declarationCountsAreNotNativeAllocationCounts'])
    def test_unreviewed_families_fail_closed(self):
        for text in (self.text()+'\nextra .delay 1;\n',self.text().replace('.functor BUFZ ','.functor UNKNOWN ',1),self.text().replace('.resolv tri,','.resolv triand,',1)):
            with self.assertRaises(ValueError):profile(text)
    def test_automatic_and_duplicate_labels_fail_closed(self):
        for text in (self.text()+'\nextra .scope autotask, "auto" "auto" 3 5, 3 5 0, S_parent;\n',self.text()+'\nrepeat .functor BUFZ 1, C4<0>;\nrepeat .functor BUFZ 1, C4<0>;\n'):
            with self.assertRaises(ValueError):profile(text)


if __name__=='__main__':unittest.main()
