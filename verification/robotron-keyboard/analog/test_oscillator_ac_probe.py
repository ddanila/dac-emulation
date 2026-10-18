"""Reject incomplete spectra and comparisons to a different transient branch."""
import json
from pathlib import Path
import tempfile
import unittest
from oscillator_ac_probe import NODES, ac_rows, summaries, reference_plateaus
from ls00_transistor_probe import sha

class AcTests(unittest.TestCase):
    def spectrum(self):
        header='frequency '+' '.join(s for s in NODES for _ in range(2))
        # Distinct complex responses, including negative real gain.
        return header+'\n'+'\n'.join(f'{10**(i/40):.17g} 1 0 1 0 2 0 -4 2 8 -4' for i in range(361))

    def test_complex_columns_and_loaded_ratios(self):
        rows=ac_rows(self.spectrum());result=summaries(rows)
        self.assertEqual(result[0]['loadedResponseRatios']['first']['real'],-2)
        self.assertEqual(result[0]['loadedResponseRatios']['first']['imaginary'],1)
        self.assertEqual(result[0]['loadedResponseRatios']['second']['real'],-2)
        self.assertAlmostEqual(result[-1]['frequencyHz'],1e9)

    def test_rejects_incomplete_nonfinite_and_reordered_spectra(self):
        lines=self.spectrum().splitlines()
        for text in ['\n'.join(lines[:-1]),'\n'.join(lines[:20]+[lines[19]]+lines[21:]),self.spectrum().replace(' 2 0',' nan 0'),self.spectrum().replace('frequency','time')]:
            with self.assertRaises(ValueError):ac_rows(text)
        rows=ac_rows(self.spectrum());rows[0][1]['v(n_OSC_RC)']=0j
        with self.assertRaises(ValueError):summaries(rows)

    def test_reference_requires_matching_model_runtime_and_artifacts(self):
        with tempfile.TemporaryDirectory()as temp:
            p=Path(temp);(p/'model.cir').write_text('test model');(p/'trace.txt').write_text('test capture')
            model=sha(p/'model.cir')
            d={'completed':True,'modelSha256':model,'connectivitySha256':'nets','engineSha256':'engine','cases':[{'amplitudeAmps':0,'stepSeconds':s,'returnedToPlateau':True,'nodes':{s:{'afterVolts':1.0}for s in NODES},'artifacts':{'trace.txt':sha(p/'trace.txt')}}for s in [1e-9,.5e-9]]}
            (p/'assessment.json').write_text(json.dumps(d))
            self.assertEqual(len(reference_plateaus(p,model,'nets','engine')),2)
            for args in [('wrong','nets','engine'),(model,'changed','engine'),(model,'nets','changed')]:
                with self.assertRaises(ValueError):reference_plateaus(p,*args)
            d['cases'][0]['nodes'][NODES[0]]['afterVolts']=float('nan')
            (p/'assessment.json').write_text(json.dumps(d))
            with self.assertRaises(ValueError):reference_plateaus(p,model,'nets','engine')
            d['cases'][0]['nodes'][NODES[0]]['afterVolts']=1.0
            (p/'assessment.json').write_text(json.dumps(d))
            (p/'trace.txt').write_text('modified')
            with self.assertRaises(ValueError):reference_plateaus(p,model,'nets','engine')

if __name__=='__main__':unittest.main()
