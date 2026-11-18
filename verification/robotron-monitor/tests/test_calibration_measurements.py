import math
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import calibration_measurements


class CalibrationMeasurementTests(unittest.TestCase):
    def rows(self, shape):
        for index in range(32*128+1):
            time=index*.001/128
            yield {'time':time,'v(eht)':11500.,'i(lhorizontal)':shape(index%128/128)}

    def test_flat_yoke_current_cannot_supply_retrace(self):
        with mock.patch.object(calibration_measurements.steady_supply,'raw_rows',
                               return_value=self.rows(lambda _:0.)):
            with self.assertRaisesRegex(ValueError,'no measurable scan swing'):
                calibration_measurements.measure('unused',start_s=0.,end_s=.032,line_s=.001,
                                                 phase_bins=128)

    def test_sinusoidal_yoke_current_is_not_a_short_retrace(self):
        with mock.patch.object(calibration_measurements.steady_supply,'raw_rows',
                               return_value=self.rows(lambda phase:math.sin(2*math.pi*phase))):
            with self.assertRaisesRegex(ValueError,'no distinct retrace excursion'):
                calibration_measurements.measure('unused',start_s=0.,end_s=.032,line_s=.001,
                                                 phase_bins=128)

    def test_missing_yoke_probe_fails_closed(self):
        rows=({'time':index*.001/128,'v(eht)':11500.}
              for index in range(32*128+1))
        with mock.patch.object(calibration_measurements.steady_supply,'raw_rows',return_value=rows):
            with self.assertRaisesRegex(ValueError,'lacks EHT or horizontal yoke probe'):
                calibration_measurements.measure('unused',start_s=0.,end_s=.032,line_s=.001,
                                                 phase_bins=128)


if __name__=='__main__':unittest.main()
