"""Refuse changed source evidence before creating or executing a replay."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from driver_boundary_replay import main, sha


class DriverBoundaryReplayTests(unittest.TestCase):
    def test_changed_deck_or_log_is_rejected_before_execution(self):
        for changed, message in [('io.cir', 'Source deck differs'),
                                 ('ngspice.log', 'Source failure log differs')]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / 'source'
                source.mkdir()
                out = Path(temporary) / 'replay'
                (source / 'io.cir').write_text('original circuit\n')
                (source / 'ngspice.log').write_text('Timestep too small\n')
                report = {'passed': False, 'assumptions': {
                    'hostBuffer': '7404-candidate', 'serialDriver': '7406-dc', 'cpuProfile': 'tv80'},
                    'deckSha256': sha(source / 'io.cir'),
                    'failureArtifacts': {'ngspice.log': {'sha256': sha(source / 'ngspice.log')}}}
                (source / 'report.json').write_text(json.dumps(report))
                (source / changed).write_text('changed evidence\n')
                with patch('sys.argv', ['replay', str(source), '--out', str(out)]):
                    with self.assertRaisesRegex(ValueError, message):
                        main()
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
