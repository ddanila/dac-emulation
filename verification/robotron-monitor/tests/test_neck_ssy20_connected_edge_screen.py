"""Check the native-video neck comparison uses aligned adaptive traces."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import neck_ssy20_connected_edge_screen as screen


class SSY20ConnectedEdgeScreenTests(unittest.TestCase):
    def test_linear_common_time_interpolation(self):
        rows=[{'time':0.,'v(cathode)':1.,'v(collector)':3.,'v(h_hot)':5.},
              {'time':1.,'v(cathode)':3.,'v(collector)':7.,'v(h_hot)':9.}]
        position, values=screen.interpolated(rows,0,.25)
        self.assertEqual(position,0)
        self.assertEqual(values,{'v(cathode)':1.5,'v(collector)':4.,'v(h_hot)':6.})

    def test_saved_native_video_receipt(self):
        saved=json.loads(screen.OUTPUT.read_text())
        work=Path(saved['run_directory'])
        if not (work/'active/trace.raw').is_file():
            self.skipTest('native connected trace artifacts are unavailable')
        self.assertEqual(screen.analyze(work),saved)
        self.assertEqual(saved['common_grid_samples'],75001)
        self.assertGreater(saved['comparison']['v(cathode)']['peak_abs_delta_v'],2)
        self.assertGreater(saved['comparison']['v(collector)']['peak_abs_delta_v'],18)
        self.assertLess(saved['comparison']['v(h_hot)']['peak_abs_delta_v'],.2)
        self.assertFalse(saved['connected_stress_qualified'])


if __name__=='__main__':
    unittest.main()
