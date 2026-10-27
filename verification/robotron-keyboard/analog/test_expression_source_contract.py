import json
import unittest
from pathlib import Path
from expression_source_contract import classify
from retained_evidence import check

HERE=Path(__file__).resolve().parent

class ExpressionSourceContract(unittest.TestCase):
    def test_retained_partition(self):
        root=HERE/'reports/expression-source-contract'
        check(root)
        board=json.loads((HERE/'reports/net-types-board/assessment.json').read_text())
        report=json.loads((root/'assessment.json').read_text())
        result=classify(board['nativeClasses']['fun'])
        self.assertEqual(result,report['observed'])
        self.assertEqual({k:v for group in result.values() for k,v in group.items()},board['nativeClasses']['fun'])
        self.assertFalse(report['qualified'])
        self.assertEqual(set(result['reduction']),{'vvp_reduce_nor'})
        self.assertEqual(set(result['concatenation']),{'vvp_fun_concat','vvp_fun_concat8'})

    def test_no_implicit_subclass_admission(self):
        names={'vvp_arith_sum':1,'vvp_arith_sum_custom':2,'vvp_arith_div':1,
               'vvp_reduce_nor_extra':1,'vvp_fun_concat_extra':1}
        result=classify(names)
        self.assertEqual(result['arithmetic'],{'vvp_arith_sum':1})
        self.assertEqual(set(result['otherFamilies']),set(names)-{'vvp_arith_sum'})

    def test_invalid_inventory(self):
        for value in ({},{'vvp_arith_sum':0},{'vvp_reduce_nor':True},{'vvp_fun_concat':1.5}):
            with self.subTest(value=value),self.assertRaises(ValueError):classify(value)

if __name__=='__main__':unittest.main()
