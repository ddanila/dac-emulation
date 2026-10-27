import unittest
from pathlib import Path
from array_source_contract import profile

BASE='S .scope module, "top" "top" 1 1;\n%end;\n'
ARRAY='A .array "words", 3 -2, 7 0;\n'


class ArraySourceContract(unittest.TestCase):
    def test_scope_ranges_and_read_port_kinds(self):
        result=profile(BASE+ARRAY+'P .array/port A, 0;\nQ .array/port A, V_address;\n')
        self.assertEqual(result['arrays'][0]['words'],6)
        self.assertEqual(result['logicalBits'],48)
        self.assertEqual([p['addressKind'] for p in result['ports']],['constant','signal'])
        self.assertEqual(result['ports'][0]['scope'],'S')

    def test_unknown_alias_automatic_and_duplicate_rejected(self):
        for extra in ('B .array/alias A;\n','B .array/net "nets", 1 0;\n',ARRAY,
                      'P .array/port MISSING, 0;\n','P .array/port A, 0;\nP .array/port A, 1;\n',
                      'Z .scope autotask, "a" "a" 1 1, 1 1 0, S;\nB .array "a", 1 0, 7 0;\n'):
            with self.assertRaises(ValueError):profile(BASE+ARRAY+extra)

    def test_retained_board_profile(self):
        here=Path(__file__).resolve().parent
        result=profile((here/'reports/wait-board/off/io.vvp').read_text())
        self.assertEqual({a['name'] for a in result['arrays']},{'rom','RegsH','RegsL'})
        self.assertTrue(all(p['array'] in {a['label'] for a in result['arrays']} for p in result['ports']))


if __name__=='__main__':unittest.main()
