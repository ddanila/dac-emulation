"""Distinguish finite recovery from branch changes and incomplete captures."""
import unittest
from oscillator_disturbance import summarize


class DisturbanceTests(unittest.TestCase):
    def rows(self,amplitude=.001,final=1):
        times=[0]+[i*1e-6 for i in range(1,11)]+[10.02e-6,10.08e-6]+[i*1e-6 for i in range(11,21)]
        return [[t,*([final if t>11e-6 else 1]*5),amplitude if 10.02e-6<=t<=10.08e-6 else 0]for t in times]

    def test_recovery_and_branch_change(self):
        self.assertTrue(summarize(self.rows(),.001,1e-6)['returnedToPlateau'])
        result=summarize(self.rows(final=.2),.001,1e-6)
        self.assertFalse(result['returnedToPlateau'])
        self.assertAlmostEqual(result['nodes']['v(n_OSC_RC)']['recoveryDifferenceVolts'],.8)

    def test_rejects_missing_pulse_and_invalid_waveform(self):
        for rows in [self.rows(amplitude=0),self.rows()[:-1],self.rows()+[self.rows()[-1]],
                     self.rows()[:-1]+[[20e-6,*([float('nan')]*6)]]]:
            with self.assertRaises(ValueError):summarize(rows,.001,1e-6)

    def test_ringing_is_not_plateau_recovery(self):
        rows=self.rows();rows[-2][2]=2.1
        result=summarize(rows,.001,1e-6)
        self.assertFalse(result['returnedToPlateau'])
        self.assertEqual(result['lateClockRisingEdges'],1)

    def test_clock_edges_use_cpu_side_of_bridge(self):
        rows=self.rows();rows[-2][1]=2.1
        self.assertEqual(summarize(rows,.001,1e-6)['lateClockRisingEdges'],0)

    def test_rejects_malformed_rows_and_invalid_inputs(self):
        for rows in [[], [[]], [[0]], [[-1e-9]+[0]*6]+self.rows()[1:]]:
            with self.assertRaises(ValueError):summarize(rows,.001,1e-6)
        for amplitude,step in [(float('nan'),1e-6),(.001,0),(.001,float('inf'))]:
            with self.assertRaises(ValueError):summarize(self.rows(),amplitude,step)


if __name__=='__main__':unittest.main()
