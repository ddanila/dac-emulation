"""Keep the provisional complementary output pair tied to catalog DC biases."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vertical_output_transistor_check as check


class VerticalOutputTransistorCheckTests(unittest.TestCase):
    def test_live_pair_matches_saved_class_comparison(self):
        saved = check.run()
        self.assertTrue(saved['passed'])
        self.assertEqual([row['source_id'] for row in saved['devices']],
                         ['012-6931:V27', '012-6931:V28'])
        for row in saved['devices']:
            self.assertTrue(all(row['checks'].values()))
            self.assertLess(row['saturation_500ma_v'], .5)

    def test_low_gain_candidate_fails_catalog_comparison_for_both_polarities(self):
        profile = json.loads(check.PROFILE.read_text())['parameters']
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)/'low-gain.cir'
            model.write_text(check.MODELS.read_text()
                             .replace('{output_bf}', '20')
                             .replace('{output_n_tf}', str(profile['output_n_tf']['nominal']))
                             .replace('{output_p_tf}', str(profile['output_p_tf']['nominal'])))
            for name, pnp, _, _ in check.SPECS.values():
                gain = check.bias_at(.15, 2, name, pnp, model)
                self.assertLess(gain['hFE'], 40)


if __name__ == '__main__':
    unittest.main()
