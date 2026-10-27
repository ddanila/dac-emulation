import unittest
from compiled_scope_profile import analyze


class ScopeProfile(unittest.TestCase):
    def test_type_and_cell_flag_are_independent(self):
        for kind,automatic in [('module',False),('task',False),('autotask',True),('function.vec4.s8',False),('autofunction.vec4.s8',True),('autobegin',True)]:
            for cell in (0,1):
                text=f'S .scope {kind}, "a" "a" 1 1, 1 1 {cell}, P;\n%end;\n'
                result=analyze(text)
                self.assertEqual(result['scopes'][0]['automatic'],automatic)
                self.assertEqual(result['scopes'][0]['isCell'],bool(cell))
                self.assertEqual(result['emitted']['automaticScopes'],automatic)

    def test_unknown_scope_type_rejected(self):
        with self.assertRaises(ValueError):analyze('S .scope autounknown, "a" "a" 1 1;\n%end;\n')


if __name__=='__main__':unittest.main()
