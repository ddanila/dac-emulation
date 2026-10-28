import json,shutil,tempfile,unittest
from pathlib import Path
from postreset_delivery_evidence import review
HERE=Path(__file__).resolve().parent
class DeliveryEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report';shutil.copytree(HERE/'reports/postreset-delivery-complete',self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_replay(self):self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_missing_input(self):
        p=self.root/'delivery.txt';lines=p.read_text().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('DELIVERY_AUDIT input '));del lines[i];p.write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'Changed complete delivery'):review(self.root)
    def test_callback_state(self):
        p=self.root/'delivery.txt';s=p.read_text();lines=s.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('DELIVERY_AUDIT output-after '));lines[i]=lines[i].replace('stop=0','stop=1');p.write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'source clamp'):review(self.root)
    def test_changed_firmware(self):
        p=self.root/'firmware.txt';p.write_text(p.read_text().replace('FIRST_FETCH','CHANGED_FETCH',1))
        with self.assertRaisesRegex(ValueError,'Changed complete firmware'):review(self.root)
    def test_short_receipt(self):
        p=self.root/'run.json';d=json.loads(p.read_text());d['endSeconds']=.00002;p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'Incomplete full capture'):review(self.root)
if __name__=='__main__':unittest.main()
