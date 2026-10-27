import unittest
from code_operand_contract import schema

SCOPE = 'S .scope module, "top" "top" 1 1;\n'
TABLE = '''
{ "%add", of_ADD, 0, {OA_NONE, OA_NONE, OA_NONE} },
{ "%addi", of_ADDI, 3, {OA_BIT1, OA_BIT2, OA_NUMBER} },
{ "%jmp", of_JMP, 1, {OA_CODE_PTR, OA_NONE, OA_NONE} },
{ "%callf/vec4", of_CALLF_VEC4, 2, {OA_CODE_PTR2, OA_VPI_PTR, OA_NONE} },
'''


class CodeOperandContract(unittest.TestCase):
    def test_typed_fields_and_labelled_instruction(self):
        result = schema(SCOPE + 'L %addi 1, 2, 3;\n%add;\n%jmp L;\n%callf/vec4 L, S;\n', TABLE)
        self.assertEqual(result['%add']['fields'], [])
        self.assertEqual([f['field'] for f in result['%addi']['fields']], ['bit_idx[0]', 'bit_idx[1]', 'number'])
        self.assertEqual([f['field'] for f in result['%callf/vec4']['fields']], ['cptr2', 'handle'])

    def test_special_vpi_forms(self):
        result = schema(SCOPE + '%vpi_call/w 1 1 "$display";\n%vpi_func/r 1 1 "$realtime";\n', TABLE)
        self.assertEqual({v['handler'] for v in result.values()}, {'of_VPI_CALL'})
        self.assertEqual({v['construction'] for v in result.values()}, {'compile_vpi_call', 'compile_vpi_func_call'})

    def test_unknown_and_synthesized_instructions_fail_closed(self):
        for text in (SCOPE + '%new/family;\n', SCOPE + '%add;\nL .ufunc/vec4 TD_f, 8;\n'):
            with self.assertRaises(ValueError):
                schema(text, TABLE)
        for table in (TABLE + TABLE, TABLE.replace('OA_NUMBER', 'OA_UNKNOWN'), TABLE.replace('of_ADDI, 3', 'of_ADDI, 2')):
            with self.assertRaises(ValueError):
                schema(SCOPE + '%addi 1, 2, 3;', table)


if __name__ == '__main__':
    unittest.main()
