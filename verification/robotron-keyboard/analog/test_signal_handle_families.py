import json,shutil,tempfile,unittest
from pathlib import Path
from signal_handle_families import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/signal-handle-families'


class SignalHandleFamilies(unittest.TestCase):
    def test_native_families_growth_and_refusals(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def tamper(self,change,mode='enabled'):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();changed=change(s);self.assertNotEqual(s,changed);p.write_text(changed)
            with self.assertRaises(ValueError):review(root)

    def test_original_integer_behavior_required(self):self.tamper(lambda s:s.replace('NO_BITS 1 number','ENDS 1 number 1 1'),'baseline')
    def test_late_family_refusal_required(self):self.tamper(lambda s:s.replace('REJECT 3 array-word\n',''))
    def test_early_family_refusal_required(self):self.tamper(lambda s:s.replace('REJECT 0 two-state\n',''))
    def test_original_wide_continuation_required(self):self.tamper(lambda s:s.replace('CONTINUE 5 -33 1','CONTINUE 5 -33 0'),'baseline')
    def test_new_handle_requires_fresh_identity(self):
        def change(s):
            a=s.splitlines();first=next(l.split()[2] for l in a if l.startswith('BIND r '));line=next(l for l in a if l.startswith('BIND late '));tokens=line.split();tokens[2]=first;return s.replace(line,' '.join(tokens))
        self.tamper(change)
    def test_native_reverse_range_mapping_required(self):
        def change(s):
            lines=s.splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('VSH_SIGNAL ') and '10signal_net' in l and l.endswith(' 4'))
            i=next(i for i in range(start+1,len(lines)) if lines[i].startswith('VSH_BIT 0 '));a=lines[i].split();a[-1]='0';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper(change)
    def test_native_alias_must_share_node_identity(self):
        def change(s):
            lines=s.splitlines();start=lines.index('IMAGE 2');i=next(i for i in range(start,len(lines)-1) if lines[i].startswith('VSH_SIGNAL ') and lines[i+1]=='VSH_NAME 6c61746500');a=lines[i].split();a[5]='999999';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper(change)


if __name__=='__main__':unittest.main()
