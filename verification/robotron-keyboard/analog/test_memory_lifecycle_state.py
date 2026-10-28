import copy,unittest
from pathlib import Path
from memory_lifecycle_state import created,without_diagnostic
from memory_metadata import parse as memory_parse
from array_probe import parse as array_parse
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
from array_compact_probe import separate
HERE=Path(__file__).resolve().parent

def image(name):
 lines=(HERE/'reports/memory-lifecycle/enabled.stdout').read_text().splitlines();start=lines.index('IMAGE '+name)+1;end=lines.index('IMAGE_END',start);lines=separate(lines[start:end])[0]
 starts=[i for i,line in enumerate(lines) if line.startswith(('VMM_BEGIN ','VAR_BEGIN ','VSM_BEGIN ','VSMR_BEGIN '))];ends=starts[1:]+[len(lines)]
 return {key:fn(lines[a:b]) for key,fn,a,b in zip(('memoryMetadata','arrays','scopeMetadata','scopeMetadataReferences'),(memory_parse,array_parse,metadata_parse,reference_parse),starts,ends)}

class State(unittest.TestCase):
 def setUp(self):
  self.before=image('before1');self.after=image('created1_0');a=self.after['arrays']['arrays'][-1]
  # The board diagnostic does not request new VPI word handles.
  a.update(cache=0,cacheParent=None,cacheWords=[])
  row=self.after['memoryMetadata']['rows'][-1];self.offset=row['handle']-row['array']
 def test_exact_addition_and_no_input_mutation(self):
  saved=copy.deepcopy(self.after);m=created(self.before,self.after,self.offset)
  self.assertEqual(m['id'],2);self.assertEqual(self.after,saved)
 def test_changed_original_word(self):
  self.after['arrays']['arrays'][0]['words'][0]='0'*8
  with self.assertRaisesRegex(ValueError,'unrelated'):created(self.before,self.after,self.offset)
 def test_foreign_owner(self):
  self.after['memoryMetadata']['rows'][-1]['scope']+=1
  with self.assertRaisesRegex(ValueError,'scope'):created(self.before,self.after,self.offset)
 def test_wrong_native_layout(self):
  with self.assertRaisesRegex(ValueError,'layout'):created(self.before,self.after,self.offset+1)
 def test_extra_cache_or_changed_payload(self):
  self.after['arrays']['arrays'][-1]['words'][1]='0'*8
  with self.assertRaisesRegex(ValueError,'payload'):created(self.before,self.after,self.offset)
 def test_original_observer_checks_preserved(self):
  old=(HERE/'parameter_late_core_review.py').read_text();new=(HERE/'memory_lifecycle_core_review.py').read_text()
  start="            state=stages['before'][1]";end='            boundary=None;stage=None'
  self.assertEqual(old[old.index(start):old.index(end)],new[new.index(start):new.index(end)])
if __name__=='__main__':unittest.main()
