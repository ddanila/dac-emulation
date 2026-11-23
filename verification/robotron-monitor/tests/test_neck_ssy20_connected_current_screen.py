"""Keep the conditional SSY20 current/power screen tied to its raw traces."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import neck_ssy20_connected_current_screen as screen


class SSY20ConnectedCurrentScreenTests(unittest.TestCase):
    def test_excursion_crossings_integrate_pulse_energy(self):
        rows=[{'time':float(t)} for t in range(4)]
        events=screen.excursions_above_reference(rows,[0.,1.4,1.4,0.])
        self.assertEqual(len(events),1)
        self.assertAlmostEqual(events[0]['start_s'],.5)
        self.assertAlmostEqual(events[0]['duration_s'],2.)
        self.assertAlmostEqual(events[0]['energy_j'],2.45)

    def test_source_limits_and_trace_receipt(self):
        saved=json.loads(screen.OUTPUT.read_text())
        work=Path(saved['work_directory'])
        edge_work=Path(saved['edge_work_directory'])
        if not (work/'active/trace.raw').is_file():
            self.skipTest('connected raw traces are unavailable')
        self.assertEqual(screen.analyze(work,edge_work),saved)
        self.assertTrue(saved['both_peak_currents_below_source_max'])
        self.assertTrue(saved['both_peak_vce_below_source_vceo'])
        self.assertTrue(saved['both_window_mean_powers_below_continuous_reference'])
        self.assertTrue(saved['any_instantaneous_power_above_continuous_reference'])
        self.assertFalse(saved['thermal_or_pulsed_soa_qualified'])
        self.assertEqual(saved['source_limits']['maximum_steady_rthja_k_per_w'],220)
        for case in saved['cases'].values():
            self.assertAlmostEqual(case['conditional_steady_mean_junction_rise_c'],
                                   case['mean_power_w']*220)
        self.assertGreater(saved['cases']['fast_candidate']['peak_instantaneous_power_w'],
                           saved['cases']['active']['peak_instantaneous_power_w'])


if __name__=='__main__':
    unittest.main()
