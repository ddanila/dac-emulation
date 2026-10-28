import json,os,shutil,tempfile,unittest
from pathlib import Path
from adc_decision_review import scan,assess
from trace_io import open_text
HERE=Path(__file__).resolve().parent
class ADCDecision(unittest.TestCase):
    def setUp(self):
        self.source=Path(os.environ.get('ADC_REPORT',HERE/'reports/adc-decision-board'))
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'off';shutil.copytree(self.source/'off',self.root)
        with open_text(self.root/'ngspice.log') as f:self.text=f.read()
    def tearDown(self):self.tmp.cleanup()
    def test_full_review(self):self.assertEqual(json.loads(json.dumps(assess(self.source))),json.loads((self.source/'assessment.json').read_text()))
    def test_threshold_rule(self):
        lines=self.text.splitlines();i=next(i for i,l in enumerate(lines) if 'ADC_CROSS' in l and 'new=0' in l);parts=lines[i].split();parts=[('value=0x1.4p+2' if s.startswith('value=') else s) for s in parts];lines[i]=' '.join(parts);(self.root/'ngspice.log').write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'threshold rule'):scan(self.root)
    def test_missing_decision(self):
        lines=self.text.splitlines();i=next(i for i,l in enumerate(lines) if 'node=fixture_clock' in l and 'old=0 new=1' in l);del lines[i];(self.root/'ngspice.log').write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'event-base match'):scan(self.root)
    def test_changed_input_value(self):
        lines=self.text.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('DELIVERY_AUDIT input ') and 'port=fixture_clk aval=1' in l);lines[i]=lines[i].replace('aval=1','aval=0');(self.root/'ngspice.log').write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'value mismatch'):scan(self.root)
    def test_cross_stream_buffering(self):
        original=scan(self.root);lines=self.text.splitlines();lines=[l for l in lines if 'ADC_CROSS' not in l]+[l for l in lines if 'ADC_CROSS' in l];(self.root/'ngspice.log').write_text('\n'.join(lines)+'\n');self.assertEqual(scan(self.root),original)
if __name__=='__main__':unittest.main()
