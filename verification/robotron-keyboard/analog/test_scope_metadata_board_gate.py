import copy,unittest
from pathlib import Path
from scope_metadata_board_review import require_typed_source,assess

class ScopeMetadataBoardGateTests(unittest.TestCase):
    def valid(self):
        return dict(reviewCompleted=True,firmwareRecordsExactlyEqual=True,negativeControls={'typed-signal-'+n+'-corrupt':{} for n in ('signed','range','node','name','cache','scope')},comparisons=dict(disabledBaseline={},enabledObserver={}),observedState=dict(boundaries=2))
    def test_prior_stage_requires_normal_and_all_typed_faults(self):
        require_typed_source(self.valid())
        for mutate in (lambda r:r.update(reviewCompleted=False),lambda r:r.update(firmwareRecordsExactlyEqual=False),lambda r:r['negativeControls'].pop('typed-signal-scope-corrupt'),lambda r:r['comparisons'].pop('enabledObserver'),lambda r:r['observedState'].update(boundaries=0)):
            r=copy.deepcopy(self.valid());mutate(r)
            with self.assertRaises(ValueError):require_typed_source(r)
    def test_retained_startup_cannot_qualify_full_capture(self):
        here=Path(__file__).resolve().parent
        with self.assertRaisesRegex(ValueError,'startup preflight is insufficient'):
            assess(here/'reports/scope-metadata-fault-preflight',here/'scope_metadata_fault_capture.py')

if __name__=='__main__':unittest.main()
