"""Keep peak interpolation and baseline timing evidence explicit."""
import json,shutil,tempfile,unittest
from pathlib import Path
import postreset_tick_peaks as peaks
import postreset_tick_firmware as firmware
import postreset_tick_events as events
ROOT=Path(__file__).resolve().parent/'reports/postreset-tick'

class TickLocalization(unittest.TestCase):
    def test_interpolation_and_exact_knots(self):
        samples=[[0.,1.],[2.,5.],[3.,3.]]
        self.assertEqual(peaks.interpolate(samples,1,1.)['value'],3.)
        self.assertTrue(peaks.interpolate(samples,1,2.)['exactSample'])
        with self.assertRaises(ValueError):peaks.interpolate(samples,1,-1.)
        with self.assertRaises(ValueError):peaks.interpolate(samples,1,4.)
        self.assertEqual(peaks.crossings(samples,1,4.),[dict(timeSeconds=1.5,rising=True),dict(timeSeconds=2.5,rising=False)])
    def test_retained_peak_evidence(self):
        root=ROOT/'peak-localization'
        self.assertEqual(peaks.review(root),json.loads((root/'assessment.json').read_text()))
    def test_retained_events(self):
        root=ROOT/'event-localization'
        self.assertEqual(events.review(root),json.loads((root/'assessment.json').read_text()))
    def test_firmware(self):
        self.assertEqual(firmware.review(ROOT),json.loads((ROOT/'firmware-comparison.json').read_text()))
    def test_peak_error_must_match_full_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'peaks';shutil.copytree(ROOT/'peak-localization',root)
            p=root/'full-assessment.json';d=json.loads(p.read_text())
            node=next(iter(d['voltageGate']['failures']))
            d['comparisons']['coarseFine']['signals'][node]['maximumAbsoluteDifference']+=1
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'reproduce'):peaks.review(root)
    def test_firmware_payload_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copy2(ROOT/'assessment.json',root/'assessment.json')
            for n in ('off','coarse','fine','finest','retry'):
                (root/n).mkdir();shutil.copy2(ROOT/n/'firmware.log',root/n/'firmware.log')
            p=root/'off/firmware.log';lines=p.read_text().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('BUS_SAMPLE '));lines[i]+=' altered';p.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError,'Non-timestamp'):firmware.review(root)

if __name__=='__main__':unittest.main()
