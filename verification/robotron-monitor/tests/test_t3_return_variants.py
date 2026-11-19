"""Keep both T3 return hypotheses and their isolated functional gap explicit."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import t3_return_variants


class T3ReturnVariantsTests(unittest.TestCase):
    def test_return_alternatives_match_archived_source_and_model(self):
        pdf=ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report=t3_return_variants.run(pdf)
        saved=json.loads((ROOT/'reference/k7222-11/t3-return-variants.json').read_text())
        self.assertEqual(report,saved)
        self.assertTrue(report['passed'])
        self.assertEqual({row['id'] for row in report['variants']},{'tied','open'})
        self.assertEqual(len(report['candidate_results']),8)
        self.assertIn('not an independent source confirmation',report['qualification'])
        self.assertTrue(all(row['tied_to_open_peak_ratio']>1000
                            for row in report['candidate_results']))


if __name__=='__main__':unittest.main()
