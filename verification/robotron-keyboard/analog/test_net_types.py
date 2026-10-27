import copy
import unittest
from pathlib import Path
import net_types_probe as types
import net_types_board as board
from net_probe import parse as graph_parse
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/net-types-board'


class NativeTypes(unittest.TestCase):
    def test_retained_native_and_board_controls(self):
        result=types.review(HERE/'reports/net-types')
        self.assertTrue(result['nativeClassBindingsMatchGraph'])
        self.assertEqual(result['restoredFaults'],36)
        result=board.review(ROOT)
        self.assertIn('vvp_fun_signal4_sa',result['nativeClasses']['fun'])
        self.assertIn('vvp_wire_vec4',result['nativeClasses']['filter'])
    def test_cross_binding_and_missing_class_rejected(self):
        graph=graph_parse((ROOT/'before.txt').read_text().splitlines())
        typed=types.parse((ROOT/'types-before.txt').read_text().splitlines())
        types.bind(graph,typed)
        bad=copy.deepcopy(typed);bad['nodes'][0]['key']+=8
        with self.assertRaises(ValueError):types.bind(graph,bad)
        lines=(ROOT/'types-before.txt').read_text().splitlines();a=lines[1].split();a[4]='-';lines[1]=' '.join(a)
        with self.assertRaises(ValueError):types.parse(lines)
    def test_unknown_abi_and_truncated_inventory_rejected(self):
        for spelling in ('99vvp_fun_force','N3foo3barE','vvp_fun_force'):
            with self.assertRaises(ValueError):types.class_name(spelling)
        lines=(ROOT/'types-before.txt').read_text().splitlines();del lines[1]
        with self.assertRaises(ValueError):types.parse(lines)


if __name__=='__main__':unittest.main()
