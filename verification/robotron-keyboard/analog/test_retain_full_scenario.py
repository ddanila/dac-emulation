import json
from pathlib import Path
import tempfile
import unittest
from compare_firmware_io import sha
from retain_full_scenario import retain,check
from test_full_scenario_refinement import levels
from test_full_scenario_review import dump


class RetentionTests(unittest.TestCase):
    def test_retains_complete_comparison_and_refuses_changed_or_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths=levels(root,[.006,.002,0]);out=root/'retained'
            for p in paths:
                (p/'capture-generator.py').write_text('# test generator\n')
                r=json.loads((p/'run.json').read_text());r['generatorSha256']=sha(p/'capture-generator.py');dump(p/'run.json',r)
            retain(paths,out);check(out)
            self.assertFalse((out/'fine/waveform.raw.xz').exists())
            with self.assertRaises(FileExistsError):retain(paths,out)
            (out/'middle/scenario.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Changed retained'):check(out)
            (paths[0]/'capture-generator.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'capture generator'):retain(paths,root/'another')


if __name__=='__main__':unittest.main()
