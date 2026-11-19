import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page10_output_pair_compare


class Page10OutputPairCompareTests(unittest.TestCase):
    def test_saved_result_and_reversed_bias_diode(self):
        source = json.loads(page10_output_pair_compare.SOURCE.read_text())
        saved = json.loads((ROOT / 'reference/k7222-11/page10-output-pair-comparison.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'vertical-output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(page10_output_pair_compare.SHEET)],
                           check=True, capture_output=True, text=True)
            self.assertEqual(page10_output_pair_compare.compare(source, xml), saved)

            changed = copy.deepcopy(source)
            changed['nets']['DIODE_19_20'].remove('V20:A')
            changed['nets']['MID_BIAS'].remove('V20:K')
            changed['nets']['DIODE_19_20'].append('V20:K')
            changed['nets']['MID_BIAS'].append('V20:A')
            changed['diode_directions'][1]['anode_net'] = 'MID_BIAS'
            changed['diode_directions'][1]['cathode_net'] = 'DIODE_19_20'
            result = page10_output_pair_compare.compare(changed, xml)
            self.assertFalse(result['passed'])
            self.assertEqual({row['pin'] for row in result['missing_or_changed_pins']
                              if row['source_id'] == '012-6931:V20'}, {'1', '2'})


if __name__ == '__main__':
    unittest.main()
