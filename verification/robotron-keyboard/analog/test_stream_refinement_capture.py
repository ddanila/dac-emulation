import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from stream_refinement_capture import capture
from test_full_scenario_refinement import levels


class StreamingScenarioTests(unittest.TestCase):
    def execute(self,root,errors=(.004,.002),mutation=None):
        dirs=levels(root,[.006,.002,0]);decks=[p/'io.cir' for p in dirs]
        for p in decks:p.write_text(p.read_text()+'.control\nset filetype=binary\nrun waveform.raw\nquit\n.endc\n.end\n')
        if mutation=='circuit':decks[1].write_text(decks[1].read_text()+'Rchanged x 0 1\n')
        if mutation=='input':(dirs[1]/'s600.hex').write_text('changed')
        def producer(builders,out,env,end,timeout):
            out.mkdir()
            for i,build in enumerate(builders):
                build(50+i)
                log='SERIAL_TX 1005000000 1\nSERIAL_RX 1005000010 1\nNo. of Data Rows : 2\n'
                if mutation=='events' and i==1:log=log.replace('1005000000','1005000001')
                if mutation=='serial':log=log.replace('1005000000','500000000').replace('1005000010','500000010')
                (out/f'{i}.log').write_text(log)
            return {'comparisons':[{'signals':{'v(x)':{'unit':'V','maximumAbsoluteDifference':v}}} for v in errors]}
        with patch('stream_refinement_capture.run',side_effect=producer),patch('stream_refinement_capture.identify',return_value=({'executable':{'path':'unused'}},{})),patch('stream_refinement_capture.verify'):
            return capture(decks,root/'out',Path('unused'),Path('unused'),10,['io.vvp','s600.hex'],{},dirs[0]/'scenario.json')

    def test_gate_and_full_scenario_windows_remain_separate(self):
        for errors,passed in [((.004,.002),True),((.001,.002),False),((.02,.015),False)]:
            with self.subTest(errors=errors),tempfile.TemporaryDirectory() as tmp:
                r=self.execute(Path(tmp),errors)
                self.assertEqual(r['voltageGatePassed'],passed)
                self.assertTrue(r['serialWindowsPassed']);self.assertFalse(r['qualified'])

    def test_changed_circuit_inputs_or_event_history_rejected(self):
        for mutation in ('circuit','input','events'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):self.execute(Path(tmp),mutation=mutation)

    def test_serial_outside_scenario_window_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.execute(Path(tmp),mutation='serial')
            self.assertFalse(r['serialWindowsPassed'])

if __name__=='__main__':unittest.main()
