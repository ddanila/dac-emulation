import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import atlas
import reference


class PublicationTests(unittest.TestCase):
    def test_failed_solver_is_not_published_as_a_fault_prediction(self):
        original=reference.run
        sheet=ROOT/'circuits/k7222-11-neck-diagnostic.kicad_sch'
        before=sheet.read_bytes()
        def failing_fault(*args,**kwargs):
            if kwargs.get('fault'):raise ValueError('injected incomplete solver output')
            return original(*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp,patch.object(reference,'run',side_effect=failing_fault):
            out=Path(tmp)/'atlas'
            index=atlas.build(out,members=2,held_out=2,only=['pullup-drift','converter-fuse-open'])
            cases={c['definition']['id']:c for c in index['cases']}
            self.assertEqual(cases['nominal']['status'],'accepted-simulation')
            self.assertEqual(cases['pullup-drift']['status'],'simulation-failed')
            self.assertEqual(cases['converter-fuse-open']['status'],'unsupported')
            self.assertNotIn('replay',cases['pullup-drift'])
            self.assertFalse((out/'public/pullup-drift.mcrt').exists())
            self.assertFalse(index['publication_gate']['first_release_eligible'])
            manifest=json.loads((out/'public/manifest.json').read_text())
            for name,item in manifest['files'].items():
                data=(out/'public'/name).read_bytes()
                self.assertEqual(len(data),item['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
        self.assertEqual(sheet.read_bytes(),before)

    def test_failed_nominal_withholds_entire_atlas(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(reference,'run',side_effect=ValueError('solver failed')):
            out=Path(tmp)/'atlas'
            with self.assertRaisesRegex(ValueError,'nominal model failed'):
                atlas.build(out,members=2,held_out=2,only=['pullup-drift'])
            self.assertFalse((out/'public/index.json').exists())
            self.assertFalse(list((out/'public').glob('*.mcrt')))


if __name__=='__main__':unittest.main()
