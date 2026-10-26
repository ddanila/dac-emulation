import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from build_delayed_corruption import DELAY, delayed


@unittest.skipUnless(shutil.which('cc'), 'C compiler required')
class DelayGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        source = cls.root / 'gate.c'
        source.write_text('#include <stdio.h>\n#include <stdlib.h>\n' + DELAY +
            '\nint main(int argc,char **argv){(void)argc;printf("%d\\n",history_corruption_due(strtod(argv[1],NULL)));return 0;}\n')
        cls.binary = cls.root / 'gate'
        subprocess.run(['cc', '-Wall', '-Werror', str(source), '-o', str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_gate(self, threshold, time):
        env = dict(os.environ)
        env.pop('ROBOTRON_HISTORY_CORRUPT_AFTER', None)
        if threshold is not None:
            env['ROBOTRON_HISTORY_CORRUPT_AFTER'] = threshold
        return subprocess.run([str(self.binary), str(time)], env=env, capture_output=True, text=True)

    def test_delayed_gate_and_default_immediate(self):
        for threshold, time, expected in [(None, 0, 1), ('0', 1e-9, 1),
                ('0.00001', 0.000009999, 0), ('0.00001', 0.00001, 1), ('0.00001', 0.00002, 1)]:
            with self.subTest(threshold=threshold, time=time):
                r = self.run_gate(threshold, time)
                self.assertEqual(r.returncode, 0)
                self.assertEqual(r.stdout.strip(), str(expected))
                self.assertEqual('HISTORY_CORRUPTION ' in r.stderr, bool(expected))

    def test_invalid_configuration_fails_closed(self):
        for value in ('', '-1', 'nan', 'inf', '1e999', '1e-999', '10us'):
            with self.subTest(value=value):
                r = self.run_gate(value, 1)
                self.assertEqual(r.returncode, 2)
                self.assertIn('Invalid history corruption start', r.stderr)


class InstrumentationTests(unittest.TestCase):
    def test_hook_requires_unique_existing_condition(self):
        text = 'static void history_rejected(struct instance *ip,char *before,double time){\nif(history_mode()==2){}}'
        result = delayed(text)
        self.assertIn('history_mode()==2&&history_corruption_due(time)', result)
        for bad in ('', text+text, result):
            with self.assertRaises(ValueError): delayed(bad)


if __name__ == '__main__':
    unittest.main()
