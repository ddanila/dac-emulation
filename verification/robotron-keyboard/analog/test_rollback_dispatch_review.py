"""Check paired-audit acceptance with deliberately corrupted controls."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from compare_firmware_io import sha
from rollback_dispatch_review import review
from test_live_raw_acceptance import fixture, write_json


def setup(root):
    pair,baseline=fixture(root)
    original=json.loads((baseline/'run.json').read_text())
    runtime={'executable':{'sha256':'diagnostic'},'spinit':{'sha256':'init'},'codeModels':[]}
    original.update(runtime=runtime,observationSignals=['v(a)'],externalDependencies=[],inputs={})
    write_json(baseline/'run.json',original)
    write_json(pair/'baseline.json',original)
    build=root/'build.json';write_json(build,{'runtimeSha256':'diagnostic'})
    for mode in ('off','on'):
        shutil.copytree(pair/'pipe',pair/mode)
        path=pair/mode/'run.json';receipt=json.loads(path.read_text())
        receipt.update(mode=mode,runtime=runtime,baselineRunSha256=sha(baseline/'run.json'),environment={'ROBOTRON_EVAL_CACHE':'off'})
        if mode=='on':receipt['environment']['ROBOTRON_ROLLBACK_AUDIT']='1'
        write_json(path,receipt)
    end=(.001).hex()
    with (pair/'on/ngspice.log').open('a') as stream:
        stream.write('ROLLBACK_AUDIT accept time=0x0p+0\n')
        for phase in ('before','after'):
            stream.write(f'ROLLBACK_AUDIT client phase={phase} time={end} name=hdl priority=1 index=0 count=1 breakpoint=0x1p+10\n')
        stream.write(f'ROLLBACK_AUDIT accept time={end}\n')
    return pair,baseline,build


def raw_setup(root):
    pair,baseline,build=setup(root)
    shutil.copyfile(pair/'off/io.cir',baseline/'io.cir')
    shutil.copyfile(pair/'off/waveform.raw',baseline/'waveform.raw')
    shutil.copyfile(pair/'off/ngspice.log',baseline/'ngspice.log')
    r=json.loads((baseline/'run.json').read_text())
    r.update(rawOutput=True,deckSha256=sha(baseline/'io.cir'),
             compressedOutput={'error':None,'streams':{'waveform.raw':{'sha256':sha(baseline/'waveform.raw')}}})
    write_json(baseline/'run.json',r);write_json(pair/'baseline.json',r)
    for mode in ('off','on'):
        path=pair/mode/'run.json';current=json.loads(path.read_text())
        current['baselineRunSha256']=sha(baseline/'run.json');write_json(path,current)
    (baseline/'completion-check.json').unlink()
    return pair,baseline,build


class RollbackReviewTests(unittest.TestCase):
    def test_complete_unchanged_pair_is_scoped_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            result=review(*setup(Path(d)))
            self.assertTrue(result['waveformsExactlyMatchBaseline'])
            self.assertFalse(result['qualified'])
            self.assertEqual(result['audit']['clientCalls'],{'hdl':1})

    def test_complete_raw_baseline_and_corruptions(self):
        with tempfile.TemporaryDirectory() as d:
            result=review(*raw_setup(Path(d)))
            self.assertTrue(result['waveformsExactlyMatchBaseline'])
            self.assertEqual(result['comparisons']['on']['waveform.raw']['samples'],2)
        for kind in ('hash','endpoint','count','sample','truncated'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                pair,baseline,build=raw_setup(Path(d))
                if kind in ('sample','truncated'):
                    p=pair/'on/waveform.raw'
                    if kind=='sample':
                        import struct
                        p.write_bytes(p.read_bytes()[:-8]+struct.pack('=d',3.0))
                    else:p.write_bytes(p.read_bytes()[:-8])
                    q=pair/'on/run.json';v=json.loads(q.read_text())
                    v['storage']['waveform.raw']['sha256']=sha(p);write_json(q,v)
                elif kind=='count':
                    p=baseline/'ngspice.log';p.write_text(p.read_text().replace('No. of Data Rows : 2','No. of Data Rows : 3'))
                else:
                    p=baseline/'run.json';r=json.loads(p.read_text())
                    if kind=='hash':r['compressedOutput']['streams']['waveform.raw']['sha256']='changed'
                    else:r['stopNs']*=2
                    write_json(p,r);write_json(pair/'baseline.json',r)
                    for mode in ('off','on'):
                        p=pair/mode/'run.json';v=json.loads(p.read_text());v['baselineRunSha256']=sha(baseline/'run.json');write_json(p,v)
                with self.assertRaises(ValueError):review(pair,baseline,build)

    def test_rejects_hidden_environment_change_or_missing_flag(self):
        for changes in ({'ROBOTRON_EVAL_CACHE':'exact'}, {'ROBOTRON_ROLLBACK_AUDIT':'0'}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as d:
                pair,baseline,build=setup(Path(d));p=pair/'on/run.json';r=json.loads(p.read_text());r['environment'].update(changes);write_json(p,r)
                with self.assertRaisesRegex(ValueError,'environment difference'):review(pair,baseline,build)

    def test_rejects_wrong_runtime_and_unlogged_endpoint(self):
        for kind in ('runtime','endpoint'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                pair,baseline,build=setup(Path(d))
                if kind=='runtime':write_json(build,{'runtimeSha256':'other'})
                else:
                    p=pair/'on/ngspice.log';p.write_text(p.read_text().replace('ROLLBACK_AUDIT accept time='+(.001).hex(),'ROLLBACK_AUDIT accept time='+(0.002).hex()))
                with self.assertRaises(ValueError):review(pair,baseline,build)


if __name__=='__main__':unittest.main()
