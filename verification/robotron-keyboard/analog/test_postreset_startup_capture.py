import json
from pathlib import Path
import tempfile
import unittest
from postreset_startup_capture import validate_source
from ttl7406_probe import sha


class PostresetSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'io.cir').write_text('Vreset reset 0 PWL(0 0 1000000n 0 1000001n 5)\n.tran 25n 1.16e+06n\n')
        (self.root / 'io.vvp').write_text('fixture')
        self.receipt = {'exitCode': 0, 'timedOut': False, 'solverDiagnostic': None,
                        'inputs': {'io.vvp': sha(self.root / 'io.vvp')},
                        'deckSha256': sha(self.root / 'io.cir'), 'environment': {}}
        self.save()

    def save(self):
        (self.root / 'run.json').write_text(json.dumps(self.receipt))

    def test_completed_unchanged_fixture_admitted(self):
        _, inputs = validate_source(self.root)
        self.assertEqual(inputs['io.cir'], self.receipt['deckSha256'])

    def test_changed_input_rejected(self):
        (self.root / 'io.vvp').write_text('different firmware')
        with self.assertRaisesRegex(ValueError, 'Changed source input'):
            validate_source(self.root)

    def test_shortened_capture_rejected_even_with_matching_hash(self):
        deck = self.root / 'io.cir'
        deck.write_text(deck.read_text().replace('1.16e+06n', '20000n'))
        self.receipt['deckSha256'] = sha(deck)
        self.save()
        with self.assertRaisesRegex(ValueError, 'unchanged 1.16-ms'):
            validate_source(self.root)

    def test_failed_or_faulted_control_rejected(self):
        for field, value in [('exitCode', 2), ('timedOut', True), ('solverDiagnostic', 'failed'), ('error', 'incomplete')]:
            with self.subTest(field=field):
                old = self.receipt.copy()
                self.receipt[field] = value
                self.save()
                with self.assertRaisesRegex(ValueError, 'completed post-reset'):
                    validate_source(self.root)
                self.receipt = old
        self.receipt['environment']['ROBOTRON_FORCE_NEWTON_REJECT'] = '1'
        self.save()
        with self.assertRaisesRegex(ValueError, 'unfaulted'):
            validate_source(self.root)


if __name__ == '__main__':
    unittest.main()
