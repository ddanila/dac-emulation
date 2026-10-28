import ast,unittest
from pathlib import Path
import build_parameter_lifecycle_bridge as subject
HERE=Path(__file__).resolve().parent
class LifecycleBridge(unittest.TestCase):
 def test_capture_logic_preserved(self):
  old=ast.parse((HERE/'parameter_late_refusal_capture.py').read_text());new=ast.parse((HERE/'parameter_lifecycle_capture.py').read_text())
  for tree in (old,new):
   tree.body.pop(0)
   for node in ast.walk(tree):
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='modes' for t in node.targets):node.value=ast.Constant('MODES')
  self.assertEqual(ast.dump(old),ast.dump(new))
 def test_built_boundary_instrumentation(self):
  path=Path('/private/tmp/k7658-parameter-lifecycle-bridge/icarus_shim.c')
  if not path.exists():self.skipTest('Local built bridge unavailable')
  source=path.read_text();self.assertIn(subject.BRANCH,source)
  self.assertIn('if(parameter_fault_done==2)return;',source)
  self.assertIn('info->vtime<6e-6',source)
  self.assertIn('parameter-lifecycle-binary',source)
  self.assertNotIn('int parameter_field=',source)
if __name__=='__main__':unittest.main()
