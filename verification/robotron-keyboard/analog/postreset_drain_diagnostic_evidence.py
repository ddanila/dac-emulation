#!/usr/bin/env python3
"""Check retained drain-refinement failure metadata without claiming waveform replay."""
import argparse,json
from pathlib import Path
from postreset_refinement_review import voltage_gate
from postreset_drain_review import validate,HERE
from ttl7406_probe import sha


def review(root,verify_archives=False):
    r=json.loads((root/'assessment.json').read_text());retention=json.loads((root/'retention.json').read_text())
    if r.get('completed') is not True or r.get('qualified') is not False or r.get('fullCampaignAccepted') is not False:raise ValueError('Changed diagnostic scope')
    if any(sha(HERE/n)!=h for n,h in r['sources'].items()):raise ValueError('Changed diagnostic source')
    if set(r['receipts'])!={'coarse','fine','finest'} or set(r['comparisons'])!={'coarseFine','fineFinest'} or set(r['firmwareRecordsExactlyEqual'])!={'coarseFine','fineFinest'}:raise ValueError('Missing diagnostic comparison')
    gate=voltage_gate(r['comparisons']['coarseFine'],r['comparisons']['fineFinest'])
    if gate!=r['voltageGate'] or r['refinementGatePassed']!=(gate['passed'] and all(r['firmwareRecordsExactlyEqual'].values())):raise ValueError('Changed unchanged-gate result')
    base=json.loads((root/'baseline/run.json').read_text());base_sha=sha(root/'baseline/run.json')
    if base_sha!=r['baselineReceiptSha256'] or base_sha!=sha(HERE/'reports/postreset-adc/25/run.json'):raise ValueError('Changed baseline identity')
    build_sha=sha(root/'coarse/candidate-build.json');bounded_sha=sha(root/'coarse/bounded-assessment.json')
    if set(retention['archives'])!={label+'/'+name for label in ('coarse','fine','finest') for name in ('ngspice.log.xz','waveform.raw.xz')}:raise ValueError('Missing local archive identity')
    for label,step in [('coarse',25),('fine',12.5),('finest',6.25)]:
        folder=root/label;receipt=json.loads((folder/'run.json').read_text())
        if sha(folder/'run.json')!=r['receipts'][label]:raise ValueError('Changed capture receipt')
        validate(receipt,base,'on',step,base_sha,build_sha,bounded_sha)
        for name,digest in receipt['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed retained input')
        if sha(folder/'candidate-build.json')!=build_sha or sha(folder/'bounded-assessment.json')!=bounded_sha:raise ValueError('Changed build/control metadata')
    if verify_archives:
        for identity in retention['archives'].values():
            p=Path(identity['path'])
            if p.stat().st_size!=identity['bytes'] or sha(p)!=identity['sha256']:raise ValueError('Changed local archive')
    return dict(qualified=False,metadataConsistent=True,archiveIdentitiesChecked=verify_archives,semanticReplayPerformed=False,refinementGatePassed=r['refinementGatePassed'],failureSignals=sorted(gate['failures']),
        scope='Retained assessment/receipt/source consistency and optional local compressed-archive identities only. Full waveform/firmware review is recorded by assessment.json; these metadata checks do not replay it or waive the unchanged gate. Large archives remain at the explicit local paths in retention.json.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--archives',action='store_true');a=p.parse_args();print(json.dumps(review(a.root,a.archives),indent=2))
