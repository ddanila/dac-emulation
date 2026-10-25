import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from compare_firmware_io import sha
from newton_retry_review import review
from test_raw_pair_review import write

END=.001006
MID=.001003


def dump(path,value):path.write_text(json.dumps(value))


def fixture(root):
    control=root/'control';evidence=root/'evidence';pair=root/'pair'
    for p in (control,evidence,pair,pair/'off',pair/'on'):p.mkdir()
    log='ROLLBACK_AUDIT accept time=0x0p+0\n'
    for t in (MID,END):
        for phase in ('before','after'):
            log+=f'ROLLBACK_AUDIT client phase={phase} time={t.hex()} name=ahdl priority=1 index=0 count=1 breakpoint=0x1p+10\n'
            if phase=='before':log+=f'TIME_AUDIT advance target={t} actual=0 base=0 tick=1e-12 pending=0\n'
        log+=f'ROLLBACK_AUDIT accept time={t.hex()}\n'
    log+='BUS_EDGE_PS 1003000000\nBUS_SAMPLE 1003000000 0000 af 0 1 0\nBUS_LATCH 1003000000 af af\nNo. of Data Rows : 3\n'
    runtime={'executable':{'path':'old','sha256':'old'},'spinit':{},'codeModels':[]}
    for name in ('io.cir','io.vvp','s600.hex','bridge.json'):(control/name).write_text(name)
    write(control/'waveform.raw',[(0,0),(MID,1),(END,1)])
    (control/'ngspice.log').write_text(log)
    r={'exitCode':0,'timedOut':False,'solverDiagnostic':None,'runtime':runtime,
       'environment':{'ROBOTRON_ROLLBACK_AUDIT':'1'},'externalDependencies':[],
       'inputs':{n:sha(control/n) for n in ('io.vvp','s600.hex')},'deckSha256':sha(control/'io.cir'),
       'storage':{'waveform.raw':{'sha256':sha(control/'waveform.raw')}}}
    dump(control/'run.json',r)
    (evidence/'run.json').write_bytes((control/'run.json').read_bytes())
    (evidence/'ngspice.log').write_text(log)
    dump(evidence/'assessment.json',{'comparisons':{'all':{'lastSeconds':END}}})
    build={'parentRuntimeSha256':'old','runtime':{'path':'new','sha256':'new'}}
    dump(pair/'build.json',build)
    for mode in ('off','on'):
        p=pair/mode
        for name in ('io.cir','io.vvp','s600.hex','bridge.json','waveform.raw'):(p/name).write_bytes((control/name).read_bytes())
        v=dict(r,mode=mode,runtime=dict(runtime,executable=build['runtime']),environment=dict(r['environment']),
               buildSha256=sha(pair/'build.json'),controlRunSha256=sha(control/'run.json'))
        text=log
        if mode=='on':
            v['environment']['ROBOTRON_FORCE_NEWTON_REJECT']='1'
            fault=f'ROLLBACK_FAULT kind=newton time={MID.hex()} original=0 injected=103\nROLLBACK_AUDIT reject kind=newton time={MID.hex()} delta=0x1p-20\n'
            text=text.replace('ROLLBACK_AUDIT client phase=before',fault+'ROLLBACK_AUDIT client phase=before',1)
        (p/'ngspice.log').write_text(text);dump(p/'run.json',v)
    return pair,control,evidence


class RetryReviewTests(unittest.TestCase):
    def test_accepts_complete_control_and_one_exercised_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch('newton_retry_review.check_bridge'):
            args=fixture(Path(tmp));r=review(*args)
            self.assertTrue(r['retryScreenPassed']);self.assertFalse(r['qualified'])

    def test_new_compressed_log_receipt_is_enforced(self):
        import lzma
        with tempfile.TemporaryDirectory() as tmp,patch('newton_retry_review.check_bridge'):
            args=fixture(Path(tmp));pair=args[0]
            for mode in ('off','on'):
                directory=pair/mode;p=directory/'ngspice.log';r=json.loads((directory/'run.json').read_text())
                r['storage']['ngspice.log']={'sha256':sha(p)}
                Path(str(p)+'.xz').write_bytes(lzma.compress(p.read_bytes()));p.unlink();dump(directory/'run.json',r)
            self.assertTrue(review(*args)['retryScreenPassed'])
            p=pair/'on/run.json';r=json.loads(p.read_text());r['storage']['ngspice.log']['sha256']='changed';dump(p,r)
            with self.assertRaisesRegex(ValueError,'Changed captured audit log'):review(*args)

    def test_selected_time_and_rejects_early_or_invalid_injection(self):
        for start in (.0010029, .001004, END, -1, float('nan'), True):
            with self.subTest(start=start), tempfile.TemporaryDirectory() as tmp, patch('newton_retry_review.check_bridge'):
                args=fixture(Path(tmp))
                for mode in ('off','on'):
                    p=args[0]/mode/'run.json';r=json.loads(p.read_text())
                    r['faultStartSeconds']=start
                    if mode=='on':r['environment']['ROBOTRON_NEWTON_REJECT_START']=repr(float(start))
                    dump(p,r)
                if start==.0010029:
                    self.assertTrue(review(*args)['retryScreenPassed'])
                else:
                    with self.assertRaises(ValueError):review(*args)

    def test_rejects_changed_inputs_environment_truncation_and_missing_retry(self):
        for mutation in ('input','environment','truncation','retry','control-history','requested-time','threshold-env'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp,patch('newton_retry_review.check_bridge'):
                args=fixture(Path(tmp));pair=args[0]
                if mutation in ('requested-time','threshold-env'):
                    p=pair/'on/run.json';r=json.loads(p.read_text())
                    if mutation=='requested-time':r['faultStartSeconds']=.0010029
                    else:r['environment']['ROBOTRON_NEWTON_REJECT_START']='.0010029'
                    dump(p,r)
                if mutation=='input':(pair/'on/io.cir').write_text('changed')
                if mutation=='environment':
                    p=pair/'on/run.json';r=json.loads(p.read_text());r['environment']['OTHER']='1';dump(p,r)
                if mutation=='truncation':(pair/'on/waveform.raw').write_bytes(b'')
                if mutation=='retry':(pair/'on/ngspice.log').write_text((pair/'off/ngspice.log').read_text())
                if mutation=='control-history':
                    p=pair/'off/ngspice.log';p.write_text(p.read_text().replace('actual=0','actual=1e-9',1))
                with self.assertRaises(ValueError):review(*args)


if __name__=='__main__':unittest.main()
