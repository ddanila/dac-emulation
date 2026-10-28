import ast,unittest
from pathlib import Path
import build_parameter_recovery_bridge as subject
HERE=Path(__file__).resolve().parent
class RecoveryBridge(unittest.TestCase):
 def test_capture_logic_preserved(self):
  trees=[ast.parse((HERE/name).read_text()) for name in ('parameter_lifecycle_capture.py','parameter_recovery_capture.py')]
  for tree in trees:tree.body.pop(0)
  self.assertEqual(ast.dump(trees[0]),ast.dump(trees[1]))
 def test_built_refusal_sequence(self):
  p=Path('/private/tmp/k7658-parameter-recovery-bridge/icarus_shim.c')
  if not p.exists():self.skipTest('Local built bridge unavailable')
  source=p.read_text();self.assertIn(subject.BRANCH,source);self.assertNotIn('VB_STAGE created',source)
  self.assertIn('if(parameter_fault_done==2)return;',source);self.assertIn('info->vtime<6e-6',source)
if __name__=='__main__':unittest.main()
