import json
from pathlib import Path
import shutil
import tempfile
import unittest
from i8282_release_probe import cases,verify

HERE=Path(__file__).resolve().parent
RETAINED=HERE/'reports/i8282-release-candidates'


class ReleaseTests(unittest.TestCase):
    def test_both_polarities_and_leakage_extremes_stay_in_source_domain(self):
        values=list(cases());self.assertEqual(len(values),108)
        self.assertEqual({c['leakageAmps'] for c in values},{-50e-6,0,50e-6})
        for c in values:
            delta=c['targetVolts']-c['initialVolts']
            self.assertAlmostEqual(delta,-.1 if c['releasedFrom']=='high' else .1)
            self.assertEqual(c['loadOhms'],180 if c['releasedFrom']=='high' else 33)
            self.assertGreater(c['stageSeconds'],0)
            self.assertAlmostEqual(c['stageSeconds']+c['maximumInternalDisconnectSeconds'],25e-9,places=20)
            for key in ('initialVolts','targetVolts','finalVolts'):self.assertTrue(.45<=c[key]<=5.25)

    def test_capacitance_reduces_available_internal_delay(self):
        values=list(cases())
        for c in values:
            if c['extraCapacitancePf']!=0:continue
            other=next(x for x in values if all(x[k]==c[k] for k in ('highOhms','supplyVolts','releasedFrom','leakageAmps')) and x['extraCapacitancePf']==30)
            self.assertAlmostEqual(other['stageSeconds']/c['stageSeconds'],1.1)
            self.assertLess(other['maximumInternalDisconnectSeconds'],c['maximumInternalDisconnectSeconds'])

    def test_retained_evidence_rejects_changed_threshold(self):
        verify(RETAINED)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(RETAINED,out)
            path=out/'assessment.json';r=json.loads(path.read_text());r['cases'][0]['case']['targetVolts']=1.5;path.write_text(json.dumps(r))
            with self.assertRaises(ValueError):verify(out)


if __name__=='__main__':unittest.main()
