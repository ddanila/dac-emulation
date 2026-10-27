import copy,unittest
from pathlib import Path
from port_payload_board_review import require_scope_source,assess

class PortPayloadBoardGateTests(unittest.TestCase):
    def valid(self):
        faults={'scope-metadata-'+n+'-corrupt':{} for n in ('units','line','function-type','function-width','function-init','intern')}
        faults.update({'callback-list-'+n+'-corrupt':{} for n in ('user','object','function','link')})
        return dict(controlsPassed=True,reviewCompleted=True,firmwareRecordsExactlyEqual=True,negativeControls=faults,comparisons=dict(disabledBaseline={},enabledObserver={}),observedState=dict(boundaries=2,scopeMetadata=dict(snapshots=4,scopes=32,boundSignals=18,metadataFull=1,metadataReused=3,referenceFull=1,referenceReused=3)))
    def test_requires_full_scope_campaign_and_complete_reconstruction(self):
        require_scope_source(self.valid())
        for mutate in (lambda r:r.update(controlsPassed=False),lambda r:r.update(reviewCompleted=False),lambda r:r.update(firmwareRecordsExactlyEqual=False),lambda r:r['negativeControls'].pop('scope-metadata-intern-corrupt'),lambda r:r['negativeControls'].pop('callback-list-link-corrupt'),lambda r:r['comparisons'].pop('enabledObserver'),lambda r:r['observedState'].update(boundaries=0),lambda r:r['observedState']['scopeMetadata'].update(snapshots=3),lambda r:r['observedState']['scopeMetadata'].update(referenceReused=2),lambda r:r['observedState']['scopeMetadata'].update(metadataFull=0,metadataReused=4)):
            r=copy.deepcopy(self.valid());mutate(r)
            with self.assertRaises(ValueError):require_scope_source(r)
    def test_startup_evidence_cannot_qualify_full_campaign(self):
        here=Path(__file__).resolve().parent
        with self.assertRaisesRegex(ValueError,'startup preflight is insufficient'):
            assess(here/'reports/port-payload-fault-preflight',here/'port_payload_fault_capture.py')

if __name__=='__main__':unittest.main()
