import tempfile
import unittest
from pathlib import Path
from build_delivery_audit_vpi import instrument,INSERTIONS,RETAINED
from delivery_audit_review import scan

class DeliveryAudit(unittest.TestCase):
    def test_only_logging_added(self):
        original=(RETAINED/'vpi.c').read_text();generated=instrument(original)
        for _,addition,_ in INSERTIONS:generated=generated.replace(addition,'')
        self.assertEqual(generated,original)
        with self.assertRaises(ValueError):instrument(original.replace(INSERTIONS[0][0],''))

    def check(self,lines):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'audit.log';p.write_text('\n'.join('DELIVERY_AUDIT '+l for l in lines)+'\n');return scan(p)

    def test_clamped_and_unclamped_transitions(self):
        lines=['input actual=1 target=2 base=1 stop=0 port=clk aval=1 bval=0',
               'output-before actual=1 target=3 base=2 stop=1 port=data aval=7 bval=2',
               'output-after actual=1 target=2 base=2 stop=0 port=data aval=7 bval=2',
               'output-before actual=2 target=3 base=1 stop=0 port=data aval=8 bval=0',
               'output-after actual=2 target=3 base=1 stop=0 port=data aval=8 bval=0']
        result=self.check(lines);self.assertEqual(result['clampedOutputGroups'],1)
        for replacement in ['target=1','target=3','target=nan']:
            changed=lines.copy();changed[2]=changed[2].replace('target=2',replacement)
            with self.assertRaises(ValueError):self.check(changed)
        with self.assertRaises(ValueError):self.check(lines[:-1])
        changed=lines.copy();changed[2]=changed[2].replace('aval=7','aval=6')
        with self.assertRaises(ValueError):self.check(changed)

if __name__=='__main__':unittest.main()
