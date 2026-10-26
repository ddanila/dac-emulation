import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from ngspice_runtime import identify
from stop_board_capture import runtime_environment
from stop_board_review import startup_identity


class StopCaptureTests(unittest.TestCase):
    def test_explicit_recorded_initialization_overrides_ambient_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);binary=p/'ngspice';binary.write_text('fixture');binary.chmod(0o755)
            model=p/'digital.cm';model.write_text('pinned model')
            init=p/'spinit';init.write_text('codemodel '+str(model)+'\n')
            runtime,_=identify(binary,init)
            base={'runtime':runtime,'environment':{'ROBOTRON_HISTORY_INIT':'on'}}
            with patch.dict(os.environ,{'SPICE_SCRIPTS':'/wrong','ROBOTRON_STALE':'bad'}):
                env=runtime_environment(base)
            self.assertEqual(env['SPICE_SCRIPTS'],str(init.resolve().parent))
            self.assertEqual(env['ROBOTRON_HISTORY_INIT'],'on');self.assertNotIn('ROBOTRON_STALE',env)
            model.write_text('changed')
            with self.assertRaises(ValueError):runtime_environment(base)

    def test_missing_initialized_model_diagnostics_rejected(self):
        good=['HISTORY_INIT seed=none initialized=1 ports=69','Instance: adrive   Message: DAC_ANCHORED enabled single-bit']
        with patch('stop_board_review.records',return_value=iter(good)):
            self.assertEqual(startup_identity(None),good)
        for lines in ([],good[:1],good[1:]):
            with patch('stop_board_review.records',return_value=iter(lines)),self.assertRaises(ValueError):startup_identity(None)


if __name__=='__main__':unittest.main()
