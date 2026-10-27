import copy,unittest
from pathlib import Path
from scope_signals_board_review import require_port_source,assess

class ScopeSignalsBoardGateTests(unittest.TestCase):
    def valid(self):
        faults={'port-payload-'+n+'-corrupt':{} for n in ('index','direction','bit-index','width','parent','name-pointer','net-reference','bit-parent','readiness')}
        faults.update({'callback-list-'+n+'-corrupt':{} for n in ('user','object','function','link')})
        return dict(controlsPassed=True,reviewCompleted=True,firmwareRecordsExactlyEqual=True,negativeControls=faults,comparisons=dict(disabledBaseline={},enabledObserver={}),observedState=dict(boundaries=2,scopeMetadata=dict(snapshots=4,scopes=32,boundSignals=18,metadataFull=1,metadataReused=3,referenceFull=1,referenceReused=3,portFull=1,portReused=3,ports=317,portBits=875)))
    def test_requires_full_scope_campaign_and_complete_reconstruction(self):
        require_port_source(self.valid())
        for mutate in (lambda r:r.update(controlsPassed=False),lambda r:r.update(reviewCompleted=False),lambda r:r.update(firmwareRecordsExactlyEqual=False),lambda r:r['negativeControls'].pop('port-payload-readiness-corrupt'),lambda r:r['negativeControls'].pop('callback-list-link-corrupt'),lambda r:r['comparisons'].pop('enabledObserver'),lambda r:r['observedState'].update(boundaries=0),lambda r:r['observedState']['scopeMetadata'].update(snapshots=3),lambda r:r['observedState']['scopeMetadata'].update(referenceReused=2),lambda r:r['observedState']['scopeMetadata'].update(portReused=2),lambda r:r['observedState']['scopeMetadata'].update(ports=0),lambda r:r['observedState']['scopeMetadata'].update(metadataFull=0,metadataReused=4)):
            r=copy.deepcopy(self.valid());mutate(r)
            with self.assertRaises(ValueError):require_port_source(r)
    def test_startup_evidence_cannot_qualify_full_campaign(self):
        here=Path(__file__).resolve().parent
        with self.assertRaisesRegex(ValueError,'startup preflight is insufficient'):
            assess(here/'reports/scope-signal-fault-preflight',here/'scope_signal_fault_capture.py')

if __name__=='__main__':unittest.main()
