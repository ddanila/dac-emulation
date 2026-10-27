import copy,json,shutil,tempfile,unittest
from pathlib import Path
from assignment_raw import HERE,parse,bind,review,output_text
from assignment_probe import parse_snapshot,review as legacy_review
from retained_evidence import check
ROOT=HERE/'reports/assignment-raw'

class AssignmentRaw(unittest.TestCase):
    def frames(self):
        lines=output_text(ROOT,'enabled').splitlines();raw=[];legacy=[]
        for start,line in enumerate(lines):
            if line.startswith('VAR_BEGIN '):
                end=next(i for i in range(start,len(lines)) if lines[i].startswith('VAR_END '));raw.append(parse(lines[start:end+1]))
            if line.startswith('VAP_BEGIN '):
                end=next(i for i in range(start,len(lines)) if lines[i].startswith('VAP_END '));legacy.append(parse_snapshot(lines[start:end+1]))
        return raw,legacy
    def test_native_evidence_replay(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_legacy_controls_on_new_runtime(self):
        root=ROOT/'legacy-controls';self.assertEqual(legacy_review(root),json.loads((root/'assessment.json').read_text()))
    def test_executing_owner_retained(self):
        raw,_=self.frames();self.assertTrue(any(e['region']=='executing' for f in raw for e in f['events']))
    def test_collision_really_hidden_by_legacy(self):
        raw,legacy=self.frames();a=raw[0];b=copy.deepcopy(a);e=next(e for e in b['events'] if e['raw'] and e['raw'][0]==0);e['raw']=b'\x88'+e['raw'][1:]
        self.assertNotEqual(a,b);bind(a,legacy[0]);bind(b,legacy[0])
    def test_legacy_target_binding(self):
        raw,legacy=self.frames();raw[0]['events'][0]['port']^=1
        with self.assertRaises(ValueError):bind(raw[0],legacy[0])
    def tamper(self,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root)
            text=output_text(root,'enabled');changed=change(text);self.assertNotEqual(text,changed)
            (root/'enabled.stdout').write_text(changed)
            with self.assertRaises(ValueError):review(root)
    def test_missing_executing_state_rejected(self):
        self.tamper(lambda s:s.replace(' executing ',' active ',1))
    def test_lifetime_rebinding_rejected(self):
        def change(s):
            lines=s.splitlines();indices=[i for i,l in enumerate(lines) if l.startswith('VAR_EVENT ')];a=lines[indices[0]].split();a[4]='999999';lines[indices[0]]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper(change)
    def test_native_output_change_rejected(self):
        self.tamper(lambda s:s.replace('ARM_VALUE 0 0 1 1 00','ARM_VALUE 0 0 1 1 88',1))
    def test_raw_width_mismatch_rejected(self):
        with self.assertRaises(ValueError):parse(['VAR_BEGIN 1 0','VAR_EVENT -1 init 0 1 0x10 0x20 0 2 00','VAR_END 1'])
    def test_duplicate_owner_rejected(self):
        row='VAR_EVENT -1 init 0 1 0x10 0x20 0 1 00'
        with self.assertRaises(ValueError):parse(['VAR_BEGIN 1 0',row,row,'VAR_END 2'])
    def test_empty_payload_and_empty_inventory(self):
        self.assertEqual(parse(['VAR_BEGIN 1 0','VAR_END 0'])['events'],[])
        self.assertEqual(parse(['VAR_BEGIN 1 0','VAR_EVENT -2 executing 0 1 0x10 0x20 0 0 -','VAR_END 1'])['events'][0]['raw'],b'')

if __name__=='__main__':unittest.main()
