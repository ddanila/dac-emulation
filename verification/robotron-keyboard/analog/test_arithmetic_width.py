import json,re,shutil,tempfile,unittest
from pathlib import Path
import arithmetic_width_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/arithmetic-widths'

class ArithmeticWidths(unittest.TestCase):
    def test_retained(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        compiled=(ROOT.parent/'arithmetic-board-budget/board.vvp').read_text()
        widths={int(m[1]) for m in re.finditer(r'\.(?:arith|cmp)/\S+ ([0-9]+),',compiled)}
        self.assertTrue(widths)
        self.assertTrue(widths<=set(result['widths']))
    def test_width_boundary_oracle(self):
        for width in (63,64,65):
            a='1'*width;b='1'+'0'*(width-1)
            self.assertEqual(probe.output(1,a,b),'0'*width)
            self.assertEqual(probe.output(2,'0'*width,b),'1'*width)
    def test_truncated_high_bit_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);shutil.copytree(ROOT,root/'copy');root=root/'copy'
            p=root/'65/disabled.stdout'
            value='ARITHMETIC_VALUE 3000 1 '+'0'+'1'*64
            text=p.read_text();self.assertIn(value,text)
            p.write_text(text.replace(value,value[:-1]))
            with self.assertRaisesRegex(ValueError,'independent oracle'):probe.review(root)
    def test_partial_receive_preserves_undriven_z(self):
        for width in probe.WIDTHS:
            a,b=probe.operands(5,width)
            self.assertEqual(a,b)
            self.assertEqual(a,'2'*(width-1)+'3')

if __name__=='__main__':unittest.main()
