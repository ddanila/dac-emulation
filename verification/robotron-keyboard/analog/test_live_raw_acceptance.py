"""Exercise live transport acceptance including receipt and truncation failures."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from live_raw_output import raw_deck
from live_raw_review import review
from compare_firmware_io import sha


def write_json(p, value):
    p.write_text(json.dumps(value))


def fixture(root):
    baseline=root/'baseline';baseline.mkdir()
    pair=root/'pair';pair.mkdir()
    for mode in ('memory','pipe'):(pair/mode).mkdir()
    deck='title\n.save v(a)\n.tran 1n 1m\n.control\nrun\nwrdata trace.txt v(a)\nquit\n.endc\n'
    (baseline/'io.cir').write_text(deck)
    original={'exitCode':0,'timedOut':False,'solverDiagnostic':None,'haltNs':None,
              'stopNs':1000000,'deckSha256':sha(baseline/'io.cir')}
    write_json(baseline/'run.json',original);write_json(pair/'baseline.json',original)
    (baseline/'trace.txt').write_text('time v(a)\n0 5\n.001 4\n')
    log='No. of Data Rows : 2\nBUS_EDGE_PS 100\nBUS_SAMPLE 100 0000 af 0 1 0\nBUS_LATCH 100 af af\nDAC_ANCHORED enabled single-bit\nMPFR_DIAGNOSTIC bits=256\nCAP_ASSEMBLY mode=1\nPOSTCAP_ASSEMBLY mode=1\n'
    (baseline/'ngspice.log').write_text(log)
    write_json(baseline/'completion-check.json',{'completed':True,'traces':{'trace.txt':{'samples':2,'sha256':sha(baseline/'trace.txt')}}})
    for mode in ('memory','pipe'):
        d=pair/mode
        (d/'io.cir').write_text(deck if mode=='memory' else raw_deck(deck)[0])
        (d/'ngspice.log').write_text(log)
        if mode=='memory':
            (d/'trace.txt').write_bytes((baseline/'trace.txt').read_bytes());name='trace.txt'
        else:
            name='waveform.raw'
            (d/name).write_bytes(b'Title: fixture\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 0\nVariables:\n0 time time\n1 v(a) voltage\nBinary:\n'+struct.pack('=4d',0,5,.001,4))
        receipt={'exitCode':0,'timedOut':False,'solverDiagnostic':None,'mode':mode,
                 'baselineRunSha256':sha(baseline/'run.json'),'deckSha256':sha(d/'io.cir'),
                 'runtime':{'fixture':True},'externalDependencies':[],'inputs':{},'environment':{},
                 'storage':{name:{'sha256':sha(d/name)}}}
        write_json(d/'run.json',receipt)
    return pair,baseline


class LiveRawAcceptanceTests(unittest.TestCase):
    def test_complete_pair_and_changed_events(self):
        with tempfile.TemporaryDirectory() as d:
            pair,baseline=fixture(Path(d))
            self.assertTrue(review(pair,baseline)['allSamplesExactlyEqual'])
            p=pair/'pipe/ngspice.log';p.write_text(p.read_text().replace('BUS_EDGE_PS 100','BUS_EDGE_PS 101'))
            with self.assertRaisesRegex(ValueError,'Firmware events'):review(pair,baseline)

    def test_failed_producer_and_changed_dependencies(self):
        for change in ({'exitCode':1},{'timedOut':True},{'runtime':{'different':True}}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                pair,baseline=fixture(Path(d));p=pair/'pipe/run.json'
                value=json.loads(p.read_text());value.update(change);write_json(p,value)
                with self.assertRaises(ValueError):review(pair,baseline)

    def test_truncation_with_updated_storage_hash_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            pair,baseline=fixture(Path(d));p=pair/'pipe/waveform.raw';p.write_bytes(p.read_bytes()[:-16])
            r=pair/'pipe/run.json';value=json.loads(r.read_text());value['storage']['waveform.raw']['sha256']=sha(p);write_json(r,value)
            with self.assertRaisesRegex(ValueError,'Truncated'):review(pair,baseline)


if __name__=='__main__':unittest.main()
