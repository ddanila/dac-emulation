import json
import lzma
from pathlib import Path
import tempfile
import unittest
from compare_firmware_io import sha
from full_scenario_refinement import review
from test_full_scenario_review import fixture,dump
from test_raw_pair_review import write


def levels(root,voltages):
    paths=[]
    for i,voltage in enumerate(voltages):
        p=root/str(i);p.mkdir();r=fixture(p);step=25/(2**i)
        deck=(p/'io.cir').read_text().replace('.tran 25n',f'.tran {step:g}n')
        (p/'io.cir').write_text(deck)
        write(p/'waveform.raw',[(0,voltage),(.00101,voltage)])
        raw=(p/'waveform.raw').read_bytes();(p/'waveform.raw.xz').write_bytes(lzma.compress(raw));(p/'waveform.raw').unlink()
        r.update(stepNs=step,deckSha256=sha(p/'io.cir'))
        r['compressedOutput']['streams']['waveform.raw']['sha256']=sha(p/'waveform.raw')
        dump(p/'run.json',r);paths.append(p)
    return paths


class RefinementTests(unittest.TestCase):
    def test_nonincreasing_sub_budget_comparison_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=review(levels(Path(tmp),[.006,.002,0]))
            self.assertTrue(r['voltageGatePassed']);self.assertFalse(r['qualified'])

    def test_gate_rejects_over_budget_and_growing_error(self):
        for voltages in ([.025,0,.02],[.005,.004,0]):
            with self.subTest(voltages=voltages),tempfile.TemporaryDirectory() as tmp:
                r=review(levels(Path(tmp),voltages))
                self.assertFalse(r['voltageGatePassed']);self.assertIn('v(x)',r['voltageFailures'])

    def test_rejects_changed_options_circuit_and_events(self):
        for mutation in ('option','circuit','events'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                paths=levels(Path(tmp),[.006,.002,0]);p=paths[1];r=json.loads((p/'run.json').read_text())
                if mutation=='option':r['experimentalOption']=True
                if mutation=='circuit':
                    (p/'io.cir').write_text((p/'io.cir').read_text()+'Rchanged x 0 10\n');r['deckSha256']=sha(p/'io.cir')
                if mutation=='events':
                    log=(p/'ngspice.log').read_text().replace('1005000000 1','1005000000 0').replace('1005000010 1','1005000010 0')
                    (p/'ngspice.log').write_text(log)
                dump(p/'run.json',r)
                with self.assertRaises(ValueError):review(paths)


if __name__=='__main__':unittest.main()
