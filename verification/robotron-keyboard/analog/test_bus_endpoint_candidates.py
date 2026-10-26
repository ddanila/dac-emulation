import json
import math
import copy
import shutil
import tempfile
from pathlib import Path
import unittest
from bus_endpoint_candidates import MODES, branch, parameters, resistance
from bus_endpoint_probe import verify

HERE = Path(__file__).resolve().parent


class EndpointCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.limits = json.loads((HERE / 'bus_limits.json').read_text())
        self.contract = json.loads((HERE / 'bus_device_contract.json').read_text())

    def test_guarantee_holds_across_supply_range_but_candidates_are_distinct(self):
        for name, conditions in self.contract['devices'].items():
            profile = self.limits['profiles'][name]
            lo, hi, _, high = parameters(profile, conditions)
            for mode in MODES:
                for i in range(101):
                    supply = lo + (hi-lo)*i/100
                    loaded = supply - resistance(profile, conditions, mode, supply)*high['sourceMagnitudeAmps']
                    self.assertGreaterEqual(loaded + 1e-12, high['minimumVolts'])
            self.assertNotEqual(resistance(profile, conditions, MODES[0], hi),
                                resistance(profile, conditions, MODES[1], hi))

    def test_no_brownout_or_unrated_supply_extrapolation(self):
        profile = self.limits['profiles']['U880']
        conditions = self.contract['devices']['U880']
        for value in (0, 2.4, 4.74, 5.26, math.inf, math.nan):
            for mode in MODES:
                with self.assertRaises(ValueError):
                    resistance(profile, conditions, mode, value)
        with self.assertRaises(ValueError):
            branch(profile, conditions, 'unknown')

    def test_retained_evidence_rejects_missing_cases_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'evidence'
            shutil.copytree(HERE / 'reports/bus-endpoint-candidates', out)
            path = out / 'assessment.json'
            original = json.loads(path.read_text())
            verify(out)
            for change in ('missing', 'voltage', 'duplicate'):
                bad = copy.deepcopy(original)
                if change == 'missing': bad['cases'].pop()
                elif change == 'duplicate': bad['cases'].append(bad['cases'][0])
                else: bad['cases'][0]['loadedHighVolts'] += .1
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError): verify(out)
            path.write_text(json.dumps(original))
            trace = out / original['cases'][0]['directory'] / 'trace.txt'
            trace.write_text(trace.read_text() + 'unexpected data')
            with self.assertRaisesRegex(ValueError, 'Changed retained DC evidence'):
                verify(out)

    def test_invalid_source_conditions_rejected(self):
        profile = self.limits['profiles']['U880']
        conditions = self.contract['devices']['U880']
        for key in ('sinkAmps', 'maximumVolts'):
            bad = json.loads(json.dumps(profile)); bad['outputLow'][key] = 0
            with self.assertRaises(ValueError):
                parameters(bad, conditions)
        with self.assertRaises(ValueError):
            parameters(profile, dict(conditions, supplyRangeVolts=[2, 5.25]))


if __name__ == '__main__':
    unittest.main()
