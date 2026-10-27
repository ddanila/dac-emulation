import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_board_faults import review
from parameter_payload import HERE
from retained_evidence import check
ROOT=HERE/'reports/parameter-board-faults'

class BoardParameterFaultTests(unittest.TestCase):
    def test_retained_board_controls(self):
        check(ROOT);actual=review(ROOT)
        self.assertEqual(actual,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(actual['exactRestorations'],20)
        self.assertEqual(actual['compiledBindingRejections'],14)
    def test_missing_refusal_or_absence_rejects(self):
        for line in ('REFUSED 1 10\n','ABSENT 2 12\n','CHANGED 1 6\n'):
            with self.subTest(line=line),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'parameter-faults.txt';s=p.read_text();self.assertIn(line,s);p.write_text(s.replace(line,'',1))
                with self.assertRaisesRegex(ValueError,'Incomplete parameter fault events'):review(root)
    def test_fault_isolation_and_restoration(self):
        for name in ('parameter-changed-1-0.txt','parameter-restored-2-11.txt','parameter-restored-1-14.txt'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/name;lines=p.read_text().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VPM_PARAM '));words=lines[i].split();words[7]=str(int(words[7])^1);lines[i]=' '.join(words);p.write_text('\n'.join(lines)+'\n')
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
