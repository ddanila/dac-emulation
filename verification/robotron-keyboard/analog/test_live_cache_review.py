import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from bridge_rollback_log import analyze
from compare_firmware_io import sha
from live_cache_review import review
from test_newton_retry_review import fixture,dump


def cache_fixture(root):
    pair,control,evidence=fixture(root)
    prior=json.loads((control/'run.json').read_text());prior['environment']['ROBOTRON_EVAL_CACHE']='off'
    dump(control/'run.json',prior);dump(evidence/'run.json',prior)
    log=(control/'ngspice.log').read_text()
    established=json.loads((evidence/'assessment.json').read_text())
    established['timing']=analyze(log.splitlines(),expected_end=.001006);dump(evidence/'assessment.json',established)
    capture=pair/'off';(capture/'capture-generator.py').write_text('# test producer\n')
    current=dict(prior,environment=dict(prior['environment'],ROBOTRON_EVAL_CACHE='exact'),
        controlRunSha256=sha(control/'run.json'),generatorSha256=sha(capture/'capture-generator.py'))
    dump(capture/'run.json',current)
    return capture,control,evidence


class CacheReviewTests(unittest.TestCase):
    def test_exact_complete_pair_is_scoped(self):
        with tempfile.TemporaryDirectory() as tmp,patch('live_cache_review.check_bridge'):
            r=review(*cache_fixture(Path(tmp)))
            self.assertTrue(r['completeWaveformComparison']['allSamplesExactlyEqual']);self.assertFalse(r['qualified'])

    def test_rejects_runtime_environment_producer_history_and_raw_changes(self):
        for mutation in ('runtime','environment','producer','history','raw'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp,patch('live_cache_review.check_bridge'):
                args=cache_fixture(Path(tmp));p=args[0];r=json.loads((p/'run.json').read_text())
                if mutation=='runtime':r['runtime']['executable']['sha256']='changed'
                if mutation=='environment':r['environment']['ROBOTRON_FORCE_NEWTON_REJECT']='1'
                if mutation=='producer':(p/'capture-generator.py').write_text('changed')
                if mutation=='history':
                    f=p/'ngspice.log';f.write_text(f.read_text().replace('actual=0','actual=1e-9',1))
                if mutation=='raw':(p/'waveform.raw').write_bytes(b'')
                dump(p/'run.json',r)
                with self.assertRaises(ValueError):review(*args)


if __name__=='__main__':unittest.main()
