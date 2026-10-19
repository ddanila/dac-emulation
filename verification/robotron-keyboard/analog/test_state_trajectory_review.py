import copy
import unittest

from state_trajectory_review import review, trials, samples


class TrajectoryTests(unittest.TestCase):
    def fixture(self):
        # Solver order includes a rejected forward trial, then a smaller saved step.
        audit = [dict(timeSeconds=t, deltaSeconds=d, newtonResult=0, order=2,
                      cableDataV=v) for t, d, v in [(1.0, 1.0, 4.0),
                                                  (1.5, .5, 20.0),
                                                  (1.25, .25, -30.0)]]
        wave = [[0, 0, 0, 0, 0, 0, 0], [1, 4, 0, 4, 0, 0, 0],
                [1.25, -30, 0, 4, 0, 0, 0]]
        return audit, wave

    def test_saved_and_unsaved_excursions_remain_distinct(self):
        audit, wave = self.fixture()
        result = review(audit, wave, .5, 2, 10)
        self.assertEqual(result['firstExcursionTrial']['timeSeconds'], 1.5)
        saved = result['firstExcursionSavedSample']
        self.assertEqual(saved['timeSeconds'], 1.25)
        self.assertEqual(saved['previousSavedTimeSeconds'], 1)
        self.assertEqual(saved['advanceVsDeltaRelativeDifference'], 0)
        self.assertEqual(result['savedBufferInputRangeV'], [4, 4])
        self.assertNotIn('savedSample', audit[0])

    def test_no_near_time_matching_or_interpolation(self):
        audit, wave = self.fixture()
        wave[-1][0] += 1e-12
        with self.assertRaises(ValueError):
            review(audit, wave, .5, 2, 10)

    def test_step_discrepancy_is_measured_without_rewriting_time(self):
        audit, wave = self.fixture()
        audit[-1]['deltaSeconds'] = .24
        last = review(audit, wave, .5, 2, 10)['trials'][-1]
        self.assertEqual(last['representedAdvanceSeconds'], .25)
        self.assertAlmostEqual(last['advanceVsDeltaRelativeDifference'], 1/24)

    def test_sample_reader_rejects_wrong_header_nonfinite_and_repeated_time(self):
        header = ('time v(n_CABLE_DATEN,host_receiver_gnd) v(n_CABLE_TAKT,host_receiver_gnd) '
                  'v(host_data_buffer_input,host_receiver_gnd) v(host_clock_buffer_input,host_receiver_gnd) '
                  'v(host_data_buffer_output,host_receiver_gnd) v(host_clock_buffer_output,host_receiver_gnd)\n')
        body = '0 0 0 0 0 0 0\n1 4 0 4 0 0 0\n'
        self.assertEqual(len(samples(header+body)), 2)
        for text in [header.replace('DATEN', 'OTHER')+body,
                     header+body.replace('1 4', '1 nan'), header+body+body]:
            with self.assertRaises(ValueError):
                samples(text)

    def test_reject_ambiguous_or_inconsistent_evidence(self):
        for case in range(4):
            audit, wave = self.fixture()
            if case == 0:
                audit.append(copy.deepcopy(audit[-1]))
            elif case == 1:
                wave[-1][1] += .001
            elif case == 2:
                audit[-1]['newtonResult'] = 103
            else:
                audit.pop()
            with self.assertRaises(ValueError):
                review(audit, wave, .5, 2, 10)

    def test_parser_uses_saved_solution_vector_and_checks_attachment(self):
        text = '''TRUNC_AUDIT solver time=0x1p+0 delta=0x1p-1 result=0 order=2
NODE_AUDIT time=0x1p+0 name=n_cable_daten rhs=0x1p+3 oldrhs=0x1.4p+2
NODE_AUDIT time=0x1p+0 name=host_receiver_gnd rhs=0x1p+1 oldrhs=0x1p+0
TRUNC_AUDIT step time=0x1p+0 proposed=0x1p+0
'''
        self.assertEqual(trials(text)[0]['cableDataV'], 4)
        with self.assertRaises(ValueError):
            trials(text.replace('name=n_cable_daten', 'name=host_receiver_gnd'))
        with self.assertRaises(ValueError):
            trials(text.replace('NODE_AUDIT time=0x1p+0', 'NODE_AUDIT time=0x1p+1'))


if __name__ == '__main__':
    unittest.main()
