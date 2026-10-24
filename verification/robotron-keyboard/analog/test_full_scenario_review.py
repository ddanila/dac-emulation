import json
import lzma
from pathlib import Path
import tempfile
import unittest
from compare_firmware_io import sha
from full_scenario_review import review
from test_raw_pair_review import write
from io_scenario import contact_source, reset_source


def dump(p,v):p.write_text(json.dumps(v))


def fixture(root):
    scenario={'name':'test','cycles':10,'contacts':[],'resets':[],
              'observations':[{'name':'press','startCycle':0,'endCycle':10,'minimumBits':1}]}
    dump(root/'scenario.json',scenario)
    sources='\n'.join(f'Vcontact{i} contact{i} 0 '+contact_source(scenario,i) for i in range(104))
    sources+='\nVfixture_reset fixture_reset 0 '+reset_source(scenario)
    sources+='\nVfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)\n'
    (root/'io.cir').write_text(sources+'.tran 25n 1010000n\n.save v(x)\n')
    (root/'io.vvp').write_text('hdl');(root/'s600.hex').write_text('00')
    write(root/'waveform.raw',[(0,0),(.00101,1)])
    (root/'waveform.raw.xz').write_bytes(lzma.compress((root/'waveform.raw').read_bytes()))
    (root/'waveform.raw').unlink()
    (root/'ngspice.log').write_text('SERIAL_TX 1005000000 1\nSERIAL_RX 1005000010 1\nNo. of Data Rows : 2\n')
    r={'exitCode':0,'timedOut':False,'solverDiagnostic':None,'rawOutput':True,
       'fullScenario':{'sha256':sha(root/'scenario.json'),'endNs':1010000},'stopNs':1010000,
       'deckSha256':sha(root/'io.cir'),'inputs':{n:sha(root/n) for n in ('io.vvp','s600.hex')},
       'observationSignals':['v(x)'],'compressedOutput':{'format':'xz','error':None,
       'streams':{'waveform.raw':{'sha256':sha(root/'waveform.raw')}}}}
    dump(root/'run.json',r)
    return r


class FullScenarioTests(unittest.TestCase):
    def test_complete_capture_and_serial_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);r=review(root)
            self.assertTrue(r['captureComplete']);self.assertTrue(r['serialWindowsPassed'])
            self.assertFalse(r['qualified'])

    def test_rejects_incomplete_extent_even_with_updated_hash_and_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=fixture(root)
            write(root/'waveform.raw',[(0,0),(.001,1)])
            r['compressedOutput']['streams']['waveform.raw']['sha256']=sha(root/'waveform.raw')
            dump(root/'run.json',r)
            with self.assertRaisesRegex(ValueError,'endpoint'):review(root)

    def test_rejects_changed_scope_failed_storage_and_absent_serial(self):
        for mutation in ('scope','storage','serial','scenario'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);r=fixture(root)
                if mutation=='scope':r['observationSignals'].append('v(missing)')
                if mutation=='storage':r['compressedOutput']['error']='failed'
                if mutation=='serial':(root/'ngspice.log').write_text('No. of Data Rows : 2\n')
                if mutation=='scenario':(root/'scenario.json').write_text('{}')
                dump(root/'run.json',r)
                with self.assertRaises(ValueError):review(root)

    def test_serial_activity_outside_required_window_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            (root/'ngspice.log').write_text('SERIAL_TX 500000000 1\nSERIAL_RX 500000010 1\nNo. of Data Rows : 2\n')
            r=review(root);self.assertTrue(r['captureComplete']);self.assertFalse(r['serialWindowsPassed'])


if __name__=='__main__':unittest.main()
