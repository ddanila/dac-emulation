#!/usr/bin/env python3
"""Operational limits must retain accepted output without changing the trajectory."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

class BudgetTests(unittest.TestCase):
    def test_state_and_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'test.c'
            source.write_text('''#include "accepted_budget.h"
#include <assert.h>
int main(void) {
    RobotronAcceptedBudget b;
    assert(!robotron_budget_init(&b, NULL, NULL));
    assert(!robotron_budget_hit(&b, 1e9));
    assert(!robotron_budget_init(&b, "2", "0.5"));
    assert(!robotron_budget_hit(&b, 0.49));
    assert(!robotron_budget_hit(&b, 0.5));
    assert(robotron_budget_hit(&b, 0.51));
    assert(robotron_budget_hit(&b, 0.52));
    assert(b.count == 2);
    assert(!robotron_budget_init(&b, "2", "0.5"));
    assert(!robotron_budget_hit(&b, 0.51));
    const char *bad[] = {"", "0", "-1", "+1", "2x", " 2", "9999999999999999999999999999999"};
    for (unsigned i=0; i<sizeof(bad)/sizeof(*bad); ++i)
        assert(robotron_budget_init(&b, bad[i], "0.5") == -1);
    const char *times[] = {"", "nan", "inf", "-1", "1x", "1e9999"};
    for (unsigned i=0; i<sizeof(times)/sizeof(*times); ++i)
        assert(robotron_budget_init(&b, "2", times[i]) == -1);
    assert(robotron_budget_init(&b, "2", NULL) == -1);
    assert(robotron_budget_init(&b, NULL, "0") == -1);
    return 0;
}
''')
            executable = Path(tmp)/'test'
            subprocess.run([shutil.which('cc'), '-std=c99', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(ROOT/'engine-patches'), str(source), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)

    @unittest.skipUnless(os.environ.get('ROBOTRON_BUDGET_RUNTIME'), 'requires patched diagnostic runtime')
    def test_capture_is_exact_prefix_and_control_continues(self):
        runtime = os.environ['ROBOTRON_BUDGET_RUNTIME']
        with tempfile.TemporaryDirectory() as tmp:
            outputs = {}
            for name, limits in [('off', {}), ('on', {'ROBOTRON_ACCEPTED_LIMIT':'3', 'ROBOTRON_ACCEPTED_AFTER':'0.0005'})]:
                directory = Path(tmp)/name
                directory.mkdir()
                (directory/'io.cir').write_text('''Budget capture
V1 in 0 PULSE(0 5 0 1u 1u 1m 2m)
R1 in out 1k
C1 out 0 1u
.tran 10u 2m
.control
set numdgt=17
set wr_singlescale
set wr_vecnames
run
wrdata trace.txt v(out)
echo AFTER_CAPTURE
quit
.endc
.end
''')
                env = {k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
                env.update(limits)
                result = subprocess.run([runtime, '-n', '-b', 'io.cir'], cwd=directory,
                                        env=env, capture_output=True, text=True, timeout=30)
                log = result.stdout+result.stderr
                self.assertEqual(result.returncode, 0, log)
                self.assertIn('AFTER_CAPTURE', log)
                self.assertEqual('ACCEPTED_BUDGET stopped' in log, name == 'on')
                outputs[name] = (directory/'trace.txt').read_text().splitlines()
            self.assertLess(len(outputs['on']), len(outputs['off']))
            self.assertEqual(outputs['on'], outputs['off'][:len(outputs['on'])])
            times = [float(line.split()[0]) for line in outputs['on'][1:]]
            self.assertEqual(sum(t >= .0005 for t in times), 3)

if __name__ == '__main__':
    unittest.main()
