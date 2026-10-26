from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import circuit_output_review as original
import test_circuit_output_review as existing
from test_circuit_output_review import FRAME
from cached_circuit_output_review import inventory_fast as candidate


class CachedInventoryTests(unittest.TestCase):
    def test_existing_contract(self):
        with patch.object(existing, 'inventory', candidate), patch.object(original, 'inventory', candidate):
            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromModule(existing).run(result)
        self.assertTrue(result.wasSuccessful(), (result.errors, result.failures))

    def test_differential_records_and_eviction(self):
        def outcome(fn,path):
         try:return ('ok',fn(path))
         except Exception as e:return ('error',type(e).__name__)
        rng=random.Random(7658);cases=0;accepted=0;rejected=0
        with tempfile.TemporaryDirectory() as tmp:
         path=Path(tmp)/'log'
         def compare(text):
          nonlocal cases,accepted,rejected
          path.write_text(text);a=outcome(original.inventory,path);b=outcome(candidate,path)
          assert a==b,(text,a,b)
          cases+=1
          if a[0]=='ok':accepted+=1
          else:rejected+=1
          return a
         # Exceed the cache capacity with valid ports, then revisit every record.
         ports=[f'C_PORT {i} {i} {i} {int(i%2==0)} device{i} node{i} 1 0 0' for i in range(2048)]
         frame='H_BEGIN callback-entry 0.000011\nC_SUM 2048\n'+'\n'.join(ports)+'\nH_END\n'
         result=compare(frame*3);assert result[0]=='ok' and result[1]['snapshots']==3
         # Identical cached records still require legal positions and snapshot context.
         for bad in (frame+ports[0]+'\n',frame+frame.replace(ports[0],ports[1]),
                     frame+frame.replace('C_SUM 2048','C_SUM 2047'),
                     frame+frame.replace(ports[1024],ports[1024].replace(' 1 0 0',' 2 0 0'))):
          assert compare(bad)[0]=='error'
         lines=FRAME.splitlines()
         for _ in range(10000):
          changed=lines.copy()
          for __ in range(rng.randrange(1,5)):
           action=rng.randrange(5);i=rng.randrange(len(changed))
           if action==0:changed.insert(i,changed[i])
           elif action==1 and len(changed)>1:changed.pop(i)
           elif action==2:rng.shuffle(changed)
           elif action==3:
            fields=changed[i].split();j=rng.randrange(len(fields));fields[j]=rng.choice(['-1','0','1','2','nan','inf','0x1p-17','C_PORT','H_END']);changed[i]=' '.join(fields)
           else:changed[i]=changed[i].replace(' ',rng.choice(['\t','  ','\u2003']))
          compare(FRAME*2+'\n'.join(changed)+'\n')
         # Independent calls must not retain prior layouts.
         assert compare(FRAME)[0]=='ok'
         assert compare(FRAME.replace('adc sense','other new_node'))[0]=='ok'
        self.assertEqual(cases, 10007)


if __name__ == '__main__':
    unittest.main()
