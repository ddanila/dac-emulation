import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from bridge_rollback_log import analyze
from retain_bridge_rollback import retain, check
from test_newton_retry_review import fixture, END
from ttl7406_probe import sha
from live_bridge_time_capture import substitute_vpi


class BridgeSubstitutionTests(unittest.TestCase):
    def test_only_explicit_library_argument_changes(self):
        deck='title\n.model hdl d_cosim simulation="/a/shim.so"\n+ lib_args=["/a/libvvp.so" "/a/ivlng.vpi"]\nV1 a 0 5\n'
        self.assertEqual(substitute_vpi(deck,'/a/ivlng.vpi','/audit/ivlng.vpi'),deck.replace('"/a/ivlng.vpi"','"/audit/ivlng.vpi"'))

    def test_rejects_duplicate_missing_or_wrong_location(self):
        for deck in ('title\n', 'V1 a 0 "/a/ivlng.vpi"\n',
                     '+ lib_args=["/a/libvvp.so" "/a/ivlng.vpi"]\n* "/a/ivlng.vpi"\n'):
            with self.subTest(deck=deck),self.assertRaises(ValueError):
                substitute_vpi(deck,'/a/ivlng.vpi','/audit/ivlng.vpi')


class BridgeRetentionTests(unittest.TestCase):
    def test_retains_raw_and_legacy_baseline_extents(self):
        for raw in (False, True):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);pair,capture,evidence=fixture(root)
                baseline=root/'baseline';baseline.mkdir()
                (baseline/'run.json').write_text(json.dumps({'rawOutput':raw}))
                extent={'waveform.raw':{'samples':3,'firstSeconds':0.0,'lastSeconds':END}}
                legacy={'completed':True,'traces':extent}
                if not raw:(baseline/'completion-check.json').write_text(json.dumps(legacy))
                (capture/'capture-generator.py').write_text('# frozen producer')
                (root/'vpi.c').write_text('/* frozen logger */')
                bridge={'libraries':{'vpi':{'path':str(root/'ivlng.vpi')}},
                        'audit':{'sourceSha256':sha(root/'vpi.c')}}
                (capture/'bridge.json').write_text(json.dumps(bridge))
                result={'comparisons':extent,'timing':analyze((capture/'ngspice.log').read_text().splitlines(),expected_end=END)}
                out=root/'retained'
                with patch('retain_bridge_rollback.review',return_value=result):
                    retain(capture,capture,baseline,capture/'bridge.json',pair/'build.json',out)
                self.assertEqual(json.loads((out/'baseline-traces.json').read_text()),extent if raw else legacy)
                check(out)
                (out/'baseline-traces.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'Changed retained'):check(out)


if __name__=='__main__':unittest.main()
