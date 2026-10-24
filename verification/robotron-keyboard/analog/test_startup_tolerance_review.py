import copy
import unittest
from startup_tolerance_review import validate_pair

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(toleranceScale=.1, toleranceComponents=['reltol'], haltNs=2000,
                         stopNs=1006000, dacAnchored=True, exitCode=0, timedOut=False,
                         solverDiagnostic=None, runtime={'sha256': 'same'},
                         samplingGridSha256='same', inputs={'rom': 'same'})
        self.candidate = {**copy.deepcopy(self.base), 'toleranceScale': .01}
        self.decks = ('.options reltol=1e-7 vntol=1e-9\nR1 a 0 1\n',
                      '.options reltol=1e-8 vntol=1e-9\nR1 a 0 1\n')
    def test_matched_controls(self):
        validate_pair(self.base, self.candidate, *self.decks)
    def test_changed_physics_and_absolute_tolerance_rejected(self):
        for deck in (self.decks[1].replace('R1 a 0 1', 'R1 a 0 2'),
                     self.decks[1].replace('vntol=1e-9', 'vntol=1e-8')):
            with self.assertRaises(ValueError):
                validate_pair(self.base, self.candidate, self.decks[0], deck)
    def test_mismatched_or_failed_controls_rejected(self):
        for field, value in [('runtime', {}), ('inputs', {}), ('samplingGridSha256', 'changed'),
                             ('haltNs', 1000), ('timedOut', True), ('exitCode', 1),
                             ('solverDiagnostic', 'failed'), ('dacAnchored', False)]:
            candidate = {**self.candidate, field: value}
            with self.assertRaises(ValueError):
                validate_pair(self.base, candidate, *self.decks)

if __name__ == '__main__':
    unittest.main()
