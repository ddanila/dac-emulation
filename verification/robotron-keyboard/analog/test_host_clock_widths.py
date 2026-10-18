import unittest
from host_clock_widths import widths

TIMING={'highWidthMinimumSeconds':180e-9,'lowWidthMinimumSeconds':180e-9,'periodMinimumSeconds':400e-9}

class WidthTests(unittest.TestCase):
    def test_long_pulses_pass_without_qualifying_censored_ends(self):
        samples=[(i*1e-9,3 if 300<=i<600 or 900<=i<1200 else 0,0)for i in range(1500)]
        r=widths(samples,TIMING)
        self.assertTrue(r['screenPassed']);self.assertFalse(r['qualified'])
        self.assertEqual([x['side']for x in r['censoredIntervals']],['left','right'])

    def test_short_and_uncertain_pulses_are_not_passes(self):
        for width,status in ((100,'fail'),(180,'indeterminate')):
            samples=[(i*1e-9,3 if 200<=i<200+width else 0,0)for i in range(500)]
            r=widths(samples,TIMING)
            high=next(x for x in r['measurements']if x['kind']=='high')
            self.assertEqual(high['status'],status);self.assertFalse(r['screenPassed'])

    def test_missing_activity_and_bad_samples(self):
        self.assertFalse(widths([(0,0,0),(1,0,0)],TIMING)['screenPassed'])
        for samples in ([],[(0,0,0)],[(0,0,0),(0,3,0)],[(0,0,0),(1,float('nan'),0)]):
            with self.assertRaises(ValueError):widths(samples,TIMING)

if __name__=='__main__':unittest.main()
