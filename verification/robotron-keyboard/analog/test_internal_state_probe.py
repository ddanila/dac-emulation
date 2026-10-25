from pathlib import Path
import tempfile
import unittest
from internal_state_probe import observations, assess, HERE
from trace_io import open_text


class StateEvidenceTests(unittest.TestCase):
    def test_retained_continuation_and_negative_controls(self):
        result=assess(HERE/'reports/internal-state')
        self.assertTrue(result['stateAndContinuationPassed'])
        self.assertTrue(result['delayedCorruptionDetectedByContinuation'])
        self.assertFalse(result['qualified'])

    def test_missing_boundary_and_changed_retry_state_rejected(self):
        for mutation in ('truncate','change'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for name in ('control','retry','register-corruption','delayed-corruption'):
                    with open_text(HERE/'reports/internal-state'/f'{name}.log') as source:
                        text=source.read()
                    if name=='retry':
                        text=text.replace('SNAPSHOT 256\n','SNAPSHOT 255\n') if mutation=='truncate' else text.replace('hdl_time ','hdl_time 99 ',1)
                    (root/f'{name}.log').write_text(text)
                with self.assertRaises(ValueError):assess(root)

if __name__=='__main__':unittest.main()
