from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import postreset_instance_review as review
import postreset_state_review as historical
from cached_circuit_output_review import inventory_fast
from test_circuit_output_review import FRAME


class CachedPostresetTests(unittest.TestCase):
    def test_isolated_globals_preserve_historical_reviewer(self):
        original = historical.inventory
        candidate = review.cached_state_reviewer()
        self.assertEqual(candidate.__code__.co_code, historical.assess.__code__.co_code)
        self.assertIsNot(candidate.__globals__, historical.assess.__globals__)
        self.assertIs(candidate.__globals__['inventory'], inventory_fast)
        self.assertIs(historical.inventory, original)
        # Keep the full waveform, firmware, history and scheduling checks.
        for name in ('compare_raw', 'equal', 'snapshots', 'scheduling', 'validate_source', 'validate_baseline'):
            self.assertIs(candidate.__globals__[name], historical.assess.__globals__[name])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log'; path.write_text(FRAME*3)
            self.assertEqual(candidate.__globals__['inventory'](path), original(path))
        self.assertIsNot(candidate.__globals__, review.cached_state_reviewer().__globals__)

    def test_full_control_call_and_instance_coverage_are_preserved(self):
        args = tuple(map(Path, ('capture', 'source', 'baseline')))
        for cached in (False, True):
            full = Mock(return_value={'comparisons': {'sentinel': True}})
            with patch.object(review, 'state_assess', full), \
                 patch.object(review, 'cached_state_reviewer', return_value=full), \
                 patch.object(review, 'inventory', return_value={'externalPendingEventObservations': 1}) as instances:
                result = review.assess(*args, cached_output=cached)
            full.assert_called_once_with(*args, fault_review=review.external_fault, summary_review=review.runtime_summary)
            instances.assert_called_once_with(args[0]/'check/ngspice.log')
            self.assertEqual(result['comparisons'], {'sentinel': True})
            self.assertEqual('cached_circuit_output_review.py' in result['reviewSources'], cached)
            with patch.object(review, 'state_assess', Mock(return_value={})), \
                 patch.object(review, 'cached_state_reviewer', return_value=Mock(return_value={})), \
                 patch.object(review, 'inventory', return_value={'externalPendingEventObservations': 0}):
                with self.assertRaisesRegex(ValueError, 'No actual external'):
                    review.assess(*args, cached_output=cached)


if __name__ == '__main__':
    unittest.main()
