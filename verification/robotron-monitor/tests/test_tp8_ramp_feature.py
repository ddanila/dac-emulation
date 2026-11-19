import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tp8_ramp_feature


class TP8RampFeatureTests(unittest.TestCase):
    def test_long_fall_excludes_reset_spike_across_resolution_and_phase(self):
        period=.0195
        times=[i*2e-6 for i in range(19500)]
        for shift in (0,.004):
            values=[]
            for time in times:
                phase=(time+shift)%period
                if phase<.001:
                    value=17.
                elif phase<.002:
                    value=17.-14.*(phase-.001)/.001
                elif phase<.0021:
                    value=3.-12.*(phase-.002)/.0001
                elif phase<.0023:
                    value=-9.+12.*(phase-.0021)/.0002
                else:
                    value=3.-10.*(phase-.0023)/(period-.0023)
                values.append(value)
            for bins in (64,128,256):
                result=tp8_ramp_feature.long_falling_ramp(
                    times,values,period,bins=bins)
                self.assertIsNotNone(result)
                self.assertAlmostEqual(result['excursion_v'],10.,delta=.3)
                self.assertGreater(result['duration_fraction'],.8)

    def test_rising_ramp_cannot_masquerade_as_long_fall(self):
        period=.0195
        times=[i*2e-6 for i in range(19500)]
        values=[10.*((time+.004)%period)/period for time in times]
        self.assertIsNone(tp8_ramp_feature.long_falling_ramp(
            times,values,period,bins=128))


if __name__=='__main__':
    unittest.main()
