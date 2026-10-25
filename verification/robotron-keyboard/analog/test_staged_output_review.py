from pathlib import Path
import tempfile
import unittest
from staged_output_review import runtime_summary,startup_stages

class StagedReviewTests(unittest.TestCase):
    def test_runtime_completion_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log'
            p.write_text('E_SUM 0x0p+0 0x0p+0 0 0 0\nNo. of Data Rows : 2\n')
            self.assertEqual(runtime_summary(p)['count'],2)
            p.write_text('No. of Data Rows : 2\nNo. of Data Rows : 2\n')
            with self.assertRaises(ValueError):runtime_summary(p)
            p.write_text('SORRY: unsupported HDL behavior\nNo. of Data Rows : 2\n')
            self.assertTrue(runtime_summary(p)['sorry'])
            p.write_text('Error: timestep too small\nNo. of Data Rows : 2\n')
            self.assertTrue(runtime_summary(p)['diagnostic'])

    def test_repeated_stages_must_share_callback(self):
        stage='H_BEGIN output-after 1e-11\nH_ARRAY 1 0 2 2:0 2:0\nE_PORT 1 0 74 1 0x0p+0 1 2 0 0\nE_PORT 1 1 75 1 0x0p+0 1 2 0 0\nH_END\n'
        callback='H_BEGIN callback-entry 1e-11\nH_END\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log';p.write_text(callback+stage+stage)
            self.assertEqual(len(startup_stages(p,{'led1':74,'led0':75})),2)
            p.write_text(callback+stage+callback+stage)
            with self.assertRaises(ValueError):startup_stages(p,{'led1':74,'led0':75})

if __name__=='__main__':unittest.main()
