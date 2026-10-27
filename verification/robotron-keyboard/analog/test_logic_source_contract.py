import json,unittest
from pathlib import Path
from logic_source_contract import classify
HERE=Path(__file__).resolve().parent

class LogicSourceContract(unittest.TestCase):
    def test_native_partition(self):
        board=json.loads((HERE/'reports/net-types-board/assessment.json').read_text())
        retained=json.loads((HERE/'reports/logic-source-contract/assessment.json').read_text())
        actual=classify(board['nativeClasses']['fun'])
        self.assertEqual(actual,retained['observed'])
        merged={k:v for group in actual.values() for k,v in group.items()}
        self.assertEqual(merged,board['nativeClasses']['fun'])
        self.assertEqual(set(actual['statelessForwarders']),{'vvp_fun_bufz','vvp_fun_buft'})
        self.assertIn('vvp_fun_muxz',actual['cachedLogic'])
    def test_unknown_subclass_is_not_stateless(self):
        result=classify({'vvp_fun_bufz':1,'vvp_fun_bufz_custom':2,'vvp_fun_muxr':3})
        self.assertEqual(result['statelessForwarders'],{'vvp_fun_bufz':1})
        self.assertEqual(result['otherFamilies'],{'vvp_fun_bufz_custom':2,'vvp_fun_muxr':3})
    def test_invalid_counts(self):
        for counts in ({},{'vvp_fun_bufz':0},{'vvp_fun_muxz':-1},{'vvp_fun_and':True},{'vvp_fun_or':1.5}):
            with self.subTest(counts=counts),self.assertRaises(ValueError):classify(counts)

if __name__=='__main__':unittest.main()
