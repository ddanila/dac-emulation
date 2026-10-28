import json,shutil,tempfile,unittest
from pathlib import Path
from postreset_drain_complete_evidence import review
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
class CompleteDrain(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report'
        shutil.copytree(HERE/'reports/postreset-drain-complete',self.root)
    def tearDown(self):self.tmp.cleanup()
    def alter(self,name,fn):
        p=self.root/name;d=json.loads(p.read_text());fn(d);p.write_text(json.dumps(d))
    def test_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_missing_record(self):
        p=self.root/'tick/firmware.txt';p.write_text('\n'.join(p.read_text().splitlines()[1:])+'\n')
        with self.assertRaisesRegex(ValueError,'Incomplete firmware'):review(self.root)
    def test_waived_gate(self):
        self.alter('full-review.json',lambda d:d.update(refinementGatePassed=True))
        with self.assertRaisesRegex(ValueError,'convergence gate'):review(self.root)
    def test_hidden_timing_change(self):
        shutil.copyfile(self.root/'off/firmware.txt',self.root/'tick/firmware.txt')
        self.alter('retention.json',lambda d:d['tick'].update(firmwareSha256=sha(self.root/'tick/firmware.txt')))
        with self.assertRaisesRegex(ValueError,'Firmware equality'):review(self.root)
    def test_changed_receipt(self):
        self.alter('retry/run.json',lambda d:d.update(endSeconds=.00002))
        with self.assertRaisesRegex(ValueError,'completed receipt'):review(self.root)
if __name__=='__main__':unittest.main()
