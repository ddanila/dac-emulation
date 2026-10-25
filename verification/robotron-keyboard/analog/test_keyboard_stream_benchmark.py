#!/usr/bin/env python3
import unittest
import json
import tempfile
from pathlib import Path
from keyboard_stream_benchmark import descendants, check
from ttl7406_probe import sha

class ProcessTreeTest(unittest.TestCase):
    def test_descendants_include_nested_children_not_unrelated_processes(self):
        rows=[(9,8,900),(4,3,40),(2,1,20),(3,2,30),(8,1,800),(1,0,10)]
        self.assertEqual(sorted(descendants(rows,2)),[(2,20),(3,30),(4,40)])
    def test_exited_root_does_not_claim_unrelated_processes(self):
        self.assertEqual(descendants([(2,1,20)],99),[])

class EvidenceTest(unittest.TestCase):
    def test_manifest_rejects_changed_evidence_and_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/'assessment.json'
            def manifest():
                (root/'manifest.json').write_text(json.dumps({'files':{'assessment.json':sha(report)},'sources':{}}))
            report.write_text(json.dumps({'qualified':False}));manifest();check(root)
            report.write_text(json.dumps({'qualified':True}))
            with self.assertRaises(ValueError):check(root)
            manifest()
            with self.assertRaises(ValueError):check(root)

if __name__=='__main__':unittest.main()
