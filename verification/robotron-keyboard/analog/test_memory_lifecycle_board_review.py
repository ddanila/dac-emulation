import json,lzma,os,tempfile,unittest
from pathlib import Path
import memory_lifecycle_board_review as subject
ROOT=Path(os.environ.get('ROBOTRON_MEMORY_LIFECYCLE_REPORT',str(Path(__file__).resolve().parent/'reports/memory-lifecycle-board')))
class BoardLifecycle(unittest.TestCase):
 def test_complete_replay(self):
  result=subject.review(ROOT)
  self.assertEqual(json.loads(json.dumps(result)),json.loads((ROOT/'assessment.json').read_text()))
  self.assertEqual(result['postRestorationActivity']['parameter-memory-lifecycle']['postFaultBusEdges'],4)
 def rejected(self,old,new):
  mode='parameter-memory-lifecycle';run=json.loads((ROOT/mode/'run.json').read_text())
  identities=subject.previous.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
  text=lzma.open(ROOT/mode/'ngspice.log.xz','rt').read();self.assertIn(old,text)
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'ngspice.log';path.write_text(text.replace(old,new,1))
   with self.assertRaises(ValueError):subject.inventory(path,identities,fault_type=mode,compiled=compiled,contract=subject.previous.port_contract(compiled),memory_offset=subject.native_layout(ROOT))
 def test_refusal_cannot_be_missing(self):
  self.rejected('changed=1 refused=1 cache_unchanged=1 restored=1','changed=1 refused=0 cache_unchanged=1 restored=1')
 def test_second_cycle_cannot_repeat_first(self):
  self.rejected('VB_MEMORY_LIFECYCLE round=2','VB_MEMORY_LIFECYCLE round=1')
 def test_logger_cache_mutation_rejects(self):
  self.rejected('cache_unchanged=1 restored=1','cache_unchanged=0 restored=1')
if __name__=='__main__':unittest.main()
