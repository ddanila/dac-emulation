"""Exercise the real diagnostic hook; this does not qualify coupled rollback."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class FaultTests(unittest.TestCase):
    def test_opt_in_threshold_and_single_converged_trial(self):
        source = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#define E_ITERLIM 103
#include "rollback_fault.h"
int main(void) {
    int fired = 0;
    unsetenv("ROBOTRON_FORCE_NEWTON_REJECT");
    assert(robotron_force_newton_reject(0, .002, &fired) == 0 && !fired);
    setenv("ROBOTRON_FORCE_NEWTON_REJECT", "0", 1);
    assert(robotron_force_newton_reject(0, .002, &fired) == 0 && !fired);
    setenv("ROBOTRON_FORCE_NEWTON_REJECT", "1", 1);
    assert(robotron_force_newton_reject(0, .0010024, &fired) == 0 && !fired);
    assert(robotron_force_newton_reject(42, .0010025, &fired) == 42 && !fired);
    assert(robotron_force_newton_reject(0, .0010025, &fired) == E_ITERLIM && fired);
    assert(robotron_force_newton_reject(0, .0010026, &fired) == 0 && fired);
    assert(robotron_force_newton_reject(42, .0010027, &fired) == 42 && fired);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(HERE / 'engine-patches'), str(root / 'test.c'),
                            '-o', str(root / 'test')], check=True)
            result = subprocess.run([str(root / 'test')], check=True,
                                    capture_output=True, text=True)
            self.assertEqual(result.stderr.count('ROLLBACK_FAULT kind=newton '), 1)


if __name__ == '__main__':
    unittest.main()
