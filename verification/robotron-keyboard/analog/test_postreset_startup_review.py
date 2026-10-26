import copy
from pathlib import Path
import tempfile
import unittest
from postreset_startup_review import inspect_log, validate_receipt
from ttl7406_probe import sha


class ReviewTests(unittest.TestCase):
    def test_rejects_unfinished_and_changed_experiment(self):
        baseline = {'environment': {}, 'externalDependencies': ['pinned']}
        inputs = {'io.cir': 'deck'}
        receipt = {'completed': True, 'exitCode': 0, 'mode': 'off', 'inputs': inputs,
                   'environment': {'ROBOTRON_HISTORY_INIT': 'off', 'ROBOTRON_STAGED_OUTPUT': 'off', 'ROBOTRON_HISTORY_STATE': 'off'},
                   'runtime': 'runtime', 'candidateBuildSha256': 'build', 'sourceRunSha256': 'source',
                   'externalDependencies': ['pinned'], 'storage': {'waveform.raw': {}},
                   'runnerSha256': sha(Path(__file__).with_name('postreset_startup_capture.py'))}
        def check(r):
            validate_receipt(r, baseline, inputs, 'off', 'runtime', 'build', 'source')
        check(receipt)
        for key, value in [('completed', False), ('error', 'timeout'), ('runtime', 'other'),
                           ('environment', {}), ('inputs', {}), ('sourceRunSha256', 'changed'),
                           ('externalDependencies', []), ('storage', {}), ('mode', 'retry')]:
            with self.subTest(key=key):
                broken = copy.deepcopy(receipt); broken[key] = value
                with self.assertRaises(ValueError):
                    check(broken)

    def test_requires_actual_firmware_after_reset_and_initializer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            log = ('FIRST_FETCH 1001501000 0000 af\nBUS_EDGE_PS 1002501280\n'
                   'BUS_SAMPLE 1002501000 0000 af 0 1 0\nBUS_LATCH 1002501000 af af\n'
                   'No. of Data Rows : 2\n')
            path.write_text(log)
            self.assertEqual(inspect_log(path, 'off')['firmwareCounts']['FIRST_FETCH'], 1)
            with self.assertRaisesRegex(ValueError, 'history initialization'):
                inspect_log(path, 'combined')
            path.write_text('HISTORY_INIT seed=none initialized=1 ports=69\n' + log)
            inspect_log(path, 'combined')
            for bad in [log.replace('BUS_EDGE_PS 1002501280', 'BUS_EDGE_PS 500'),
                        log.replace('FIRST_FETCH', 'NOT_A_FETCH'), log.replace('af af', 'af ff')]:
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    inspect_log(path, 'off')


if __name__ == '__main__':
    unittest.main()
