import json,unittest
from pathlib import Path
from signal_source_contract import profile
HERE=Path(__file__).resolve().parent
BASE='S .scope module, "top" "top" 1 1;\n%end;\n'
VAR='V .var "value", 7 0;\n'

class SignalSourceContract(unittest.TestCase):
    def test_ranges_and_integer_profile(self):
        result=profile(BASE+VAR+'I .var/i "index", 0 31;\n')
        self.assertEqual([s['width'] for s in result['signals']],[8,32])
        self.assertEqual(result['logicalBits'],40)
        self.assertEqual(result['signals'][0]['scope'],'S')
    def test_unknown_automatic_duplicate_and_missing_scope(self):
        for text in (BASE+VAR+VAR,BASE+'R .var/real "r", 0 0;\n',
                     BASE+'S2 .scope autotask, "a" "a" 1 1, 1 1 0, S;\n'+VAR,
                     BASE+'.scope UNKNOWN;\n'+VAR,BASE+'B .var/2u "b", 7 0;\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):profile(text)
    def test_retained_board_and_native_count(self):
        result=profile((HERE/'reports/net-types-board/board.vvp').read_text())
        retained=json.loads((HERE/'reports/signal-source-contract/assessment.json').read_text())
        self.assertEqual(result,retained['compiled'])
        native=json.loads((HERE/'reports/net-types-board/assessment.json').read_text())
        self.assertEqual(len(result['signals']),native['nativeClasses']['fun']['vvp_fun_signal4_sa'])

if __name__=='__main__':unittest.main()
