import unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
class RecoveryCore(unittest.TestCase):
 def test_all_existing_observer_checks_preserved(self):
  old=(HERE/'parameter_late_core_review.py').read_text();new=(HERE/'parameter_recovery_core_review.py').read_text();start="            state=stages['before'][1]";end='            boundary=None;stage=None'
  self.assertEqual(old[old.index(start):old.index(end)],new[new.index(start):new.index(end)])
 def test_no_diagnostic_population_removed(self):
  source=(HERE/'parameter_recovery_board_review.py').read_text()
  self.assertNotIn('without_diagnostic',source)
  self.assertIn("parameter_bindings(pending['parameters'],pending['metadata'],pending['reference'],kwargs['compiled'])",source)
if __name__=='__main__':unittest.main()
