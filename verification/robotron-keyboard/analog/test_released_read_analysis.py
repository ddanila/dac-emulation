import unittest
from released_read_analysis import analyze


class ReleasedReadAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(2048)
        self.rom[0x32:0x36] = bytes.fromhex('cbf8ed40')
        self.rom[0x57:0x5b] = bytes.fromhex('ed400844')

    def graph(self, middle):
        return {0x57: 'IN B,(C)', 0x5b: "EX AF,AF'", **middle,
                0x70: 'JP 0057h'}

    def test_repeated_arbitrary_reads_cleared_before_branch(self):
        result = analyze(self.rom, self.graph({0x5c: 'BIT 0,A', 0x5e: 'JR Z,0070h'}))
        self.assertFalse(result['observableDependencyFound'])
        self.assertIn(0x57, result['visitedOffsets'])

    def test_alternate_flags_cannot_drive_branch(self):
        with self.assertRaisesRegex(ValueError, 'affects flags read'):
            analyze(self.rom, self.graph({0x5c: 'JR Z,0070h'}))

    def test_carry_is_independent_but_rotate_preserves_sign(self):
        analyze(self.rom, self.graph({0x5c: 'JR C,0070h'}))
        with self.assertRaisesRegex(ValueError, 'affects flags read'):
            analyze(self.rom, self.graph({0x5c: 'RRCA', 0x5d: 'JR M,0070h'}))

    def test_word_add_does_not_clear_zero_flag(self):
        with self.assertRaisesRegex(ValueError, 'affects flags read'):
            analyze(self.rom, self.graph({0x5c: 'ADD HL,SP', 0x5d: 'JR Z,0070h'}))

    def test_missing_byte_discard_is_rejected(self):
        self.rom[0x5a] = 0
        with self.assertRaisesRegex(ValueError, 'discard sequence'):
            analyze(self.rom, self.graph({0x5c: 'BIT 0,A'}))

    def test_unsupported_flag_export_and_indirect_jump_fail_closed(self):
        for instruction in ('PUSH AF', 'JP (HL)'):
            with self.subTest(instruction=instruction), self.assertRaises(ValueError):
                analyze(self.rom, self.graph({0x5c: instruction}))


if __name__ == '__main__':
    unittest.main()
