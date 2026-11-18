import subprocess
import sys
import tempfile
import unittest
import math
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import grid_geometry
import lab
import steady_supply


class GridGeometryTests(unittest.TestCase):
    def test_source_grid_markers_measure_scan_extents_and_spacing(self):
        subprocess.run(['make','build/robotron-signal-pattern'],cwd=ROOT.parents[1],
                       check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            capture=Path(directory)/'grid.json'
            capture.write_bytes(subprocess.check_output(
                [str(ROOT.parents[1]/'build/robotron-signal-pattern'),'grid',
                 '--fields','4','--line-characters','108']))
            data=lab.parse_capture(capture);selection=steady_supply.select(data)
            line=selection['line_period_ticks']/data['clock_hz'];start=.0585;end=.078
            active_s=8320/data['clock_hz']
            targets,_,_=grid_geometry.marker_times(selection,data['clock_hz'],start)
            times=sorted({0.,start,end,*[t for t,_ in targets]})
            def rows():
                for t in times:
                    relative=max(0.,t-start)
                    n=math.floor(relative/line+1e-9)
                    phase=relative-n*line
                    yield {'time':t,'v(eht)':11500.,'v(g2)':400.,'v(g4)':200.,
                           'v(cathode)':20.,
                           'i(lhorizontal)':-.105+.21*phase/active_s,
                           'i(lvertical)':-.0725+.145*(n-24)/287}
            def ray(anode,grid2,focus,ih,iv,*,overrides):
                self.assertAlmostEqual(anode,11480.)
                self.assertEqual(overrides,{})
                return {'landed':True,'x_m':ih,'y_m':iv}
            with mock.patch.object(grid_geometry.steady_supply,'raw_rows',return_value=rows()):
                result=grid_geometry.measure('unused',selection,data['clock_hz'],
                    start_s=start,end_s=end,field={},ray_solver=ray)
            self.assertAlmostEqual(result['picture_width_mm'],210.,delta=2.)
            self.assertAlmostEqual(result['picture_height_mm'],145.,delta=2.)
            self.assertLess(result['horizontal_linearity'],.1)
            self.assertLess(result['vertical_linearity'],.1)
            self.assertEqual(result['horizontal_marker_rows'],9)


if __name__=='__main__':unittest.main()
