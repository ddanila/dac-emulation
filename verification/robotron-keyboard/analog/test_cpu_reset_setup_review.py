import unittest
from cpu_reset_setup_review import observe


def sample(t,clk,rst=0,vcc=5,unc=0):return (t*1e-9,clk,rst,vcc,unc*1e-9)


class ResetSetupTests(unittest.TestCase):
    def test_voltage_rise_bracket_uses_earliest_edge(self):
        good=[sample(0,0),sample(100,0),sample(110,2),sample(120,5)]
        self.assertEqual(observe(good,120e-9,150)['setupObserved']['low'],1)
        bad=[sample(0,0),sample(80,0),sample(110,2),sample(120,5)]
        r=observe(bad,120e-9,150)
        self.assertEqual(r['setupObserved']['low'],0)
        self.assertEqual(r['setupNotEstablished'],1)
        self.assertFalse(r['qualified'])

    def test_supply_dip_and_reset_unknown_break_stability(self):
        for mid in (sample(50,0,vcc=2),sample(50,0,rst=1.5),sample(50,0,rst=6)):
            r=observe([sample(0,0),mid,sample(80,0),sample(100,5)],100e-9,100)
            self.assertEqual(r['setupObserved']['low'],0)

    def test_deassertion_and_timestamp_uncertainty_do_not_borrow_old_low_time(self):
        r=observe([sample(0,0),sample(100,0,rst=5),sample(110,5,rst=5)],110e-9,150)
        self.assertEqual(r['setupObserved']['high'],0)
        r=observe([sample(0,0,unc=1),sample(90,0,unc=1),sample(100,5,unc=1)],100e-9,100)
        self.assertEqual(r['setupObserved']['low'],0)

    def test_high_excursion_and_complete_aligned_window_required(self):
        r=observe([sample(0,0),sample(100,0),sample(110,3)],110e-9,100)
        self.assertEqual(r['rises'],0)
        for samples,end,step in [([sample(0,0),sample(100,5)],200e-9,100),
                                 ([sample(0,0),sample(100,5)],100e-9,10),
                                 ([sample(0,0),sample(100,float('nan'))],100e-9,100)]:
            with self.assertRaises(ValueError):observe(samples,end,step)


if __name__=='__main__':unittest.main()
