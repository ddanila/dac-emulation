import json
from pathlib import Path
import shutil
import tempfile
import unittest
from i8282_enabled_candidates import cases, deck, evaluate, verify
from bus_switching_probe import duration

HERE=Path(__file__).resolve().parent
RETAINED=HERE/'reports/i8282-enabled-candidates'


class EnabledCandidatesTests(unittest.TestCase):
    def test_all_published_conditions_and_distinct_alternatives(self):
        matrix=list(cases())
        self.assertEqual({(c['highOhms'],c['supplyVolts'],c['kind']) for c in matrix},
                         {(r,v,k) for r in (125.,250.) for v in (4.5,5.,5.5) for k in ('dc-high','dc-low','rise','fall')})
        for c in matrix:
            if c['kind']=='dc-high':self.assertGreaterEqual(c['expectedVolts'],c['limitVolts'])
            elif c['kind']=='dc-low':self.assertLessEqual(c['expectedVolts'],c['limitVolts'])
            else:self.assertLess(c['expectedSeconds'],c['maximumSeconds'])
        spec=json.loads((HERE/'bus_switching_limits.json').read_text())
        self.assertGreater(duration(4.5,420,spec['switchingLoad'],.8,2),spec['rise']['maximumSeconds'])

    def test_invalid_measurements_cannot_pass(self):
        c=next(cases())
        for log in ('', 'v(out) = nan\n', 'v(out) = 1\n','v(out) = 3.875\nv(out) = 3.875\n'):
            with self.assertRaises(ValueError):evaluate(c,log)

    def test_retained_evidence_and_tampered_deck(self):
        verify(RETAINED)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(RETAINED,out)
            path=out/'0/probe.cir';path.write_text(path.read_text().replace('125','420'))
            with self.assertRaises(ValueError):verify(out)


if __name__=='__main__':unittest.main()
