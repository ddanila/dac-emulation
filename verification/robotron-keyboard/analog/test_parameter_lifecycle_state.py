import copy,unittest
from pathlib import Path
from parameter_lifecycle_state import created
from parameter_payload import parse as parameter_parse
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
HERE=Path(__file__).resolve().parent

def image(name):
 lines=(HERE/'reports/parameter-lifecycle/enabled.stdout').read_text().splitlines();start=lines.index('IMAGE '+name)+1;end=lines.index('IMAGE_END',start);lines=lines[start:end]
 starts=[i for i,line in enumerate(lines) if line.startswith(('VPM_BEGIN ','VSM_BEGIN ','VSMR_BEGIN '))];ends=starts[1:]+[len(lines)]
 return {key:fn(lines[a:b]) for key,fn,a,b in zip(('parameters','scopeMetadata','scopeMetadataReferences'),(parameter_parse,metadata_parse,reference_parse),starts,ends)}

class State(unittest.TestCase):
 def setUp(self):
  self.before=image('before1');self.states={}
  for n,kind in enumerate(('binary','real','string')):
   after=image(f'created1_{n}')
   # Board modes run independently, so each family's first allocation is serial 1.
   after['parameters']['rows'][-1]['name']=f'__parameter_lifecycle_{n}_1\0'.encode().hex()
   self.states[kind]=after
 def test_all_families_and_no_input_mutation(self):
  for kind,after in self.states.items():
   with self.subTest(kind=kind):
    saved=copy.deepcopy(after);p=created(self.before,after,kind);self.assertEqual(p['kind'],kind);self.assertEqual(after,saved)
 def test_changed_original_value(self):
  after=self.states['binary'];after['parameters']['rows'][0]['value']['words'][0][0]^=1
  with self.assertRaisesRegex(ValueError,'unrelated'):created(self.before,after,'binary')
 def test_lost_high_unknown_bit(self):
  after=self.states['binary'];after['parameters']['rows'][-1]['value']['words'][1][1]^=1
  with self.assertRaisesRegex(ValueError,'binary payload'):created(self.before,after,'binary')
 def test_lost_embedded_null(self):
  after=self.states['string'];after['parameters']['rows'][-1]['value']['value']='47205200'
  with self.assertRaisesRegex(ValueError,'string payload'):created(self.before,after,'string')
 def test_wrong_family(self):
  with self.assertRaisesRegex(ValueError,'family'):created(self.before,self.states['real'],'binary')
 def test_foreign_owner(self):
  after=self.states['real'];after['parameters']['rows'][-1]['scope']+=1
  with self.assertRaisesRegex(ValueError,'scope'):created(self.before,after,'real')
 def test_original_observer_checks_preserved(self):
  old=(HERE/'parameter_late_core_review.py').read_text();new=(HERE/'parameter_lifecycle_core_review.py').read_text();start="            state=stages['before'][1]";end='            boundary=None;stage=None'
  self.assertEqual(old[old.index(start):old.index(end)],new[new.index(start):new.index(end)])
if __name__=='__main__':unittest.main()
