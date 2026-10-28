import ast,copy,unittest
from pathlib import Path
import parameter_operational_review as parameter
import parameter_fault_review
HERE=Path(__file__).resolve().parent

class ParameterOperationalReview(unittest.TestCase):
    def test_prior_full_campaign_checks_preserved(self):
        original=(HERE/'scope_signals_board_review.py').read_text()
        changed=(HERE/'parameter_operational_review.py').read_text()
        old="('scope-signal-signed-corrupt', 'scope-signal-range-corrupt', 'scope-signal-node-corrupt', 'scope-signal-name-corrupt', 'scope-signal-cache-corrupt', 'scope-signal-scope-corrupt')"
        new="tuple('parameter-'+n+'-corrupt' for n in ('word','signed','sized','local','file','line','name','width','scope','name-pointer'))"
        self.assertEqual(changed.count(new),2)
        changed=changed.replace(new,old).replace('require(prior)','require_port_source(prior)')
        def function(source):
            f=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='assess')
            for node in ast.walk(f):
                if isinstance(node,ast.Dict):
                    for i,key in enumerate(node.keys):
                        if isinstance(key,ast.Constant) and key.value=='scope':node.values[i]=ast.Constant(value='documented scope')
            return ast.dump(f)
        self.assertEqual(function(changed),function(original))
        self.assertIs(parameter.inventory,parameter_fault_review.inventory)

    def test_startup_evidence_cannot_qualify(self):
        with self.assertRaisesRegex(ValueError,'complete normal and fault campaign'):
            parameter.assess(HERE/'reports/parameter-class-board',HERE/'parameter_operational_capture.py')

if __name__=='__main__':unittest.main()
