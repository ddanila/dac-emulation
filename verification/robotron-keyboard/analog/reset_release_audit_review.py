#!/usr/bin/env python3
"""Review a live failure audit and independently solve its frozen terminal systems."""
import argparse
import json
import lzma
import math
import shutil
from pathlib import Path
from linear_system_review import parse,review
from linear_precision_review import solve
from live_transition_review import audit_stats,diagnostic
from reset_release_driver_review import trace_summary,completed,TRACES
from host_waveform_comparison import rows,compare_samples
from numerical_voltage_budget import voltage_gate
from network_refinement_review import events
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
CASES=('disabled','enabled','mpfr-local','refined-25','refined-12.5','refined-6.25')

def frozen_review(log):
    systems,incomplete=parse(log)
    if incomplete:raise ValueError('Incomplete frozen matrix capture')
    result=[]
    for system in systems[-2:]:
        low,high=solve(system,64),solve(system,96)
        feed=next(i for i,n in system['names'].items() if n=='xdata.feed')
        exact=review(system)
        result.append({'id':system['id'],'timeSeconds':exact['timeSeconds'],'iteration':exact['iteration'],
            'recordedFeedVolts':float(system['x'][feed]),'independentFeedVolts':float(high[feed]),
            'maximum64to96SolutionDifference':max(float(abs(low[i]-high[i])) for i in low),
            'normwiseBackwardError':exact['normwiseBackwardError'],
            'worstAbsoluteResidual':exact['worstAbsoluteResidual'],
            'scope':'Independent 64/96 decimal-digit solutions of the same recorded, already-rounded linear coefficients. Does not reconstruct device loading, rerun Newton iteration or qualify the physical driver.'})
    return result

def retain(root,out):
    out.mkdir(parents=True,exist_ok=False);cases={};receipts={};captured={}
    for name in CASES:
        src=root/name;dst=out/name;dst.mkdir()
        run=json.loads((src/'run.json').read_text());log=(src/'ngspice.log').read_text();receipts[name]=run
        if not run.get('externalDependencies'):raise ValueError('Missing external runtime fingerprints')
        if sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Changed deck')
        for file,digest in run['inputs'].items():
            if sha(src/file)!=digest:raise ValueError('Changed runtime input')
        if run['toleranceScale']!=1 or run['matrixBoundarySubstitution'] or not run['physicalDriverTrace']:
            raise ValueError('Changed circuit or tolerance scope')
        for file in ('io.cir','run.json'):shutil.copyfile(src/file,dst/file)
        with (src/'ngspice.log').open('rb') as stream,lzma.open(dst/'ngspice.log.xz','wb',preset=3) as compressed:shutil.copyfileobj(stream,compressed)
        traces={file:trace_summary(src/file) for file in TRACES if (src/file).exists()};captured[name]=traces
        (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        failure=diagnostic(log)
        cases[name]={'completed':completed(run,traces,failure),'timedOut':run['timedOut'],
                     'diagnostic':failure,'requestedEndSeconds':run['stopNs']*1e-9,
                     'lastSeconds':{file:t['lastSeconds'] for file,t in traces.items()}}
    for run in receipts.values():
        for key in ('runtime','externalDependencies','inputs','sourceDeckSha256'):
            if run[key]!=receipts['disabled'][key]:raise ValueError('Different runtime or circuit inputs')
    identical=all(captured['disabled'][file]['sha256']==captured['enabled'][file]['sha256'] for file in TRACES)
    if not identical:raise ValueError('Audit logging changed retained waveforms')
    log=(root/'enabled/ngspice.log').read_text();stats=audit_stats(log)
    pairs=[];refined=('refined-25','refined-12.5','refined-6.25')
    if all(cases[name]['completed'] for name in refined):
        for a,b in zip(refined,refined[1:]):
            signals=receipts[a]['observationSignals']
            if signals!=receipts[b]['observationSignals']:raise ValueError('Different saved vectors')
            result=compare_samples(rows(root/a/'network_witness.txt',signals,receipts[a]['stepNs']),rows(root/b/'network_witness.txt',signals,receipts[b]['stepNs']))
            pair={'coarse':a,'fine':b,'endSeconds':result['endSeconds'],'signals':{signal:{'unit':'V' if signal.lower().startswith('v(') else 'A','maximumAbsoluteDifference':value['maximumDifferenceV'],'timeSeconds':value['timeSeconds']} for signal,value in zip(signals,result['signals'])}}
            ea,eb=events((root/a/'ngspice.log').read_text()),events((root/b/'ngspice.log').read_text())
            pair['busEventsIdentical']=ea==eb;pair['busSamplesIdentical']=ea['samples']==eb['samples']
            pair['busEdgeTimingDifferencePs']=[y-x for x,y in zip(ea['edgeTimesPs'],eb['edgeTimesPs'])] if len(ea['edgeTimesPs'])==len(eb['edgeTimesPs']) else None
            pair['latchesMatch']=ea['latchesMatch'] and eb['latchesMatch'];pairs.append(pair)
    result={'schema':1,'cases':cases,'auditWaveformsByteIdentical':identical,'audit':stats,
            'frozenTerminalSystems':frozen_review(log),'refinementPairs':pairs,
            'voltageGate':voltage_gate(pairs) if len(pairs)==2 else None,
            'numericallyQualified':False,'electricallyQualified':False,'productionDefaultChangeAuthorized':False,
            'scope':'Bounded live direct-driver circuit through reset release. Failed controls are retained. Frozen-system corrections and successful short captures cannot establish full-repeat convergence or device applicability. No alignment or omitted failing interval is used to admit refinement.',
            'sources':{name:sha(HERE/name) for name in ('reset_release_audit_review.py','live_transition_probe.py','eval_cache_benchmark.py','linear_system_review.py','linear_precision_review.py','live_transition_review.py','reset_release_driver_review.py','host_waveform_comparison.py','numerical_voltage_budget.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(files,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runs',type=Path);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:
        for name,digest in json.loads((args.out/'manifest.json').read_text()).items():
            if sha(args.out/name)!=digest:raise ValueError('Changed retained evidence: '+name)
        print('Retained reset-release audit hashes verified; qualification remains separate')
    else:
        if args.runs is None:parser.error('--runs is required')
        result=retain(args.runs,args.out);print(json.dumps(result['cases'],indent=2))
