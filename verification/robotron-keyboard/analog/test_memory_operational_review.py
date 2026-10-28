import ast,unittest
from pathlib import Path
import memory_operational_review as memory
import memory_fault_review
HERE=Path(__file__).resolve().parent

class MemoryOperationalReview(unittest.TestCase):
    def test_prior_full_campaign_checks_preserved(self):
        original=(HERE/'parameter_operational_review.py').read_text()
        changed=(HERE/'memory_operational_review.py').read_text()
        old="tuple('parameter-'+n+'-corrupt' for n in ('word','signed','sized','local','file','line','name','width','scope','name-pointer'))"
        new="tuple('memory-'+n+'-corrupt' for n in ('name','name-pointer','cache-pointer','port-head','storage-pointer'))"
        self.assertEqual(changed.count(new),2)
        self.assertEqual(changed.count('memory_offset=offset'),2)
        self.assertEqual(changed.count('offset=native_layout(root)'),1)
        changed=changed.replace(new,old).replace('    offset=native_layout(root)\n','').replace(',memory_offset=offset','')
        def function(source):
            f=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='assess')
            for node in ast.walk(f):
                if isinstance(node,ast.Dict):
                    for i,key in enumerate(node.keys):
                        if isinstance(key,ast.Constant) and key.value=='scope':node.values[i]=ast.Constant(value='documented scope')
            return ast.dump(f)
        self.assertEqual(function(changed),function(original))
        self.assertIs(memory.inventory,memory_fault_review.inventory)

    def test_startup_evidence_cannot_qualify(self):
        with self.assertRaisesRegex(ValueError,'complete normal and fault campaign'):
            memory.assess(HERE/'reports/parameter-late-refusal-controls',HERE/'memory_operational_capture.py')

if __name__=='__main__':unittest.main()
