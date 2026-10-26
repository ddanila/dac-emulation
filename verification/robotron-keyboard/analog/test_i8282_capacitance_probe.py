import json
from pathlib import Path
import shutil
import tempfile
import unittest
from i8282_capacitance_probe import budgets,cases,deck,verify
from bus_switching_probe import duration

HERE=Path(__file__).resolve().parent
RETAINED=HERE/'reports/i8282-capacitance-candidates'


class CapacitanceTests(unittest.TestCase):
    def test_existing_fixture_combination_is_rejected(self):
        values=list(cases())
        self.assertEqual(len(values),36)
        for c in values:
            expected=not (c['highOhms']==250 and c['supplyVolts']==4.5 and c['kind']=='rise' and c['extraCapacitancePf']>0)
            self.assertEqual(c['withinPublishedLimit'],expected)
        c=next(c for c in values if c['extraCapacitancePf']==12)
        self.assertIn('Cdevice out 0 ',deck(c))
        self.assertIn('Cload out 0 ',deck(c))

    def test_both_edges_constrain_capacitance_and_bound_is_tight(self):
        spec=json.loads((HERE/'bus_switching_limits.json').read_text())
        for b in budgets():
            bound=b['maximumExtraCapacitancePf']
            self.assertGreater(bound,0)
            for fraction in (.999,1.001):
                load=dict(spec['switchingLoad']);load['capacitanceFarads']+=bound*fraction*1e-12
                times=[duration(b['supplyVolts'] if edge=='rise' else 0,b['highOhms'] if edge=='rise' else 22.5,
                                load,spec[edge]['fromVolts'],spec[edge]['toVolts'])/spec[edge]['maximumSeconds'] for edge in ('rise','fall')]
                self.assertEqual(max(times)<=1,fraction<1)

    def test_retained_failure_cannot_be_relabelled_as_success(self):
        verify(RETAINED)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(RETAINED,out)
            path=out/'assessment.json';r=json.loads(path.read_text())
            next(c for c in r['cases'] if not c['case']['withinPublishedLimit'])['case']['withinPublishedLimit']=True
            path.write_text(json.dumps(r))
            with self.assertRaises(ValueError):verify(out)


if __name__=='__main__':unittest.main()
