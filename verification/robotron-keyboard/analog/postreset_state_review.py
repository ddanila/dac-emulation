#!/usr/bin/env python3
"""Review full post-reset observer controls and intentional negative captures."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from audit_log import equal
from circuit_output_review import external_fault, inventory, runtime_summary
from event_state_review import scheduling
from history_state_review import snapshots
from postreset_startup_capture import validate_source
from postreset_startup_review import END, FIRMWARE, inspect_log, validate_receipt as validate_baseline
from postreset_state_capture import VARIANTS
from raw_pair_review import compare_raw
from trace_io import open_binary
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent
SOURCE_NAMES = ('postreset_state_capture.py','bounded_log_process.py','postreset_startup_capture.py','compressed_output.py')


def validate_receipt(r, prior, inputs, mode, runtime, build, source_digest):
    expected_exit = 2 if mode in ('immediate','delayed') else 0
    if not r.get('completed') or r.get('error') or r.get('timedOut'):
        raise ValueError('Incomplete state capture')
    if r['mode'] != mode or r['exitCode'] != expected_exit or r['expectedExitCode'] != expected_exit:
        raise ValueError('Unexpected termination')
    if r['inputs'] != inputs or r['sourceRunSha256'] != source_digest or r['externalDependencies'] != prior['externalDependencies']:
        raise ValueError('Mismatched fixture or dependencies')
    if r['runtime'] != runtime or r['candidateBuildSha256'] != build:
        raise ValueError('Different candidate runtime')
    if r['environment'] != dict(prior['environment'],**VARIANTS[mode]):
        raise ValueError('Different experimental conditions')
    if r['sources'] != {name:sha(HERE/name) for name in SOURCE_NAMES}:
        raise ValueError('Changed state capture sources')
    limits=r['limits']; log=r['log']
    if any(type(limits[k]) is not int or limits[k] <= 0 for k in ('logicalLogBytes','compressedLogBytes','freeSpaceReserveBytes')):
        raise ValueError('Invalid capture limits')
    if not math.isfinite(limits['timeoutSeconds']) or limits['timeoutSeconds'] <= 0:
        raise ValueError('Invalid capture timeout')
    if log['exitCode'] != expected_exit or log['logicalLimitBytes'] != limits['logicalLogBytes'] or log['compressedLimitBytes'] != limits['compressedLogBytes']:
        raise ValueError('Log budget/termination mismatch')
    if not 0 < log['bytes'] <= limits['logicalLogBytes'] or not 0 < log['compressedBytes'] <= limits['compressedLogBytes']:
        raise ValueError('Log exceeds declared budget')
    if set(r['storage']) != {'waveform.raw'}: raise ValueError('Missing raw capture')


def stream_info(path):
    h=hashlib.sha256();size=0
    with open_binary(path) as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):
            h.update(data);size+=len(data)
    return {'sha256':h.hexdigest(),'bytes':size}


def assess(root, source, baseline, *, fault_review=None, summary_review=None):
    review_fault=fault_review or external_fault
    summarize=summary_review or runtime_summary
    prior, inputs=validate_source(source); source_digest=sha(source/'run.json')
    base=json.loads((baseline/'run.json').read_text())
    validate_baseline(base,prior,inputs,'combined',base['runtime'],sha(HERE/'reports/startup-fixes/build.json'),source_digest)
    if base['runtime']['executable'] != prior['runtime']['executable']:
        raise ValueError('Changed baseline executable')
    for name,digest in inputs.items():
        if sha(baseline/name)!=digest: raise ValueError('Changed baseline input')
    if stream_info(baseline/'waveform.raw')!=base['storage']['waveform.raw'] or stream_info(baseline/'ngspice.log')['sha256']!=base['logSha256']:
        raise ValueError('Changed baseline stream')
    baseline_log=inspect_log(baseline/'ngspice.log','combined')
    runs={m:json.loads((root/m/'run.json').read_text()) for m in VARIANTS}
    runtime=runs['off']['runtime'];build=sha(root/'off/build.json')
    if runtime['executable']!=prior['runtime']['executable']: raise ValueError('Changed state executable')
    summaries={};histories={};faults={}
    for mode,r in runs.items():
        folder=root/mode
        validate_receipt(r,prior,inputs,mode,runtime,build,source_digest)
        if sha(folder/'build.json')!=build: raise ValueError('Changed retained model build')
        for name,digest in inputs.items():
            if sha(folder/name)!=digest: raise ValueError('Changed retained input')
        if stream_info(folder/'waveform.raw')!=r['storage']['waveform.raw']:
            raise ValueError('Changed state waveform')
        log=stream_info(folder/'ngspice.log')
        if log!={k:r['log'][k] for k in ('sha256','bytes')} or (folder/'ngspice.log.xz').stat().st_size!=r['log']['compressedBytes']:
            raise ValueError('Changed retained log or budget usage')
        negative=mode in ('immediate','delayed')
        if mode!='off':
            stats={}
            for _ in snapshots(folder/'ngspice.log',stats,corrupt=negative): pass
            histories[mode]=stats
        if negative:
            faults[mode]=review_fault(folder/'ngspice.log',float(VARIANTS[mode]['ROBOTRON_HISTORY_CORRUPT_AFTER']))
        else:
            summaries[mode]=summarize(folder/'ngspice.log')
            s=summaries[mode]
            if s['count'] is None or s['diagnostic'] or s['sorry']: raise ValueError('Incomplete positive log')
    comparisons={}
    for name,folder,count in [('disabledBaseline',baseline,baseline_log['count']),('enabledObserver',root/'check',summaries['check']['count'])]:
        comparisons[name]=compare_raw(root/'off/waveform.raw',folder/'waveform.raw',[summaries['off']['count'],count],END,exact=True)
        if not equal(root/'off/ngspice.log',folder/'ngspice.log',FIRMWARE): raise ValueError('Changed firmware continuation')
    queues=inventory(root/'check/ngspice.log')
    if not queues['otherModelPendingEventObservations']: raise ValueError('Missing external pending events')
    return {'completed':True,'qualified':False,'scope':'Complete 1.16-ms positive controls; negative controls intentionally abort. External clock/reset, not startup or supply recovery.',
            'comparisons':comparisons,'histories':histories,'corruption':faults,'circuitOutputs':queues,
            'scheduling':scheduling(root/'check/ngspice.log'),
            'receipts':{m:sha(root/m/'run.json') for m in VARIANTS},'baselineReceiptSha256':sha(baseline/'run.json'),
            'notEstablished':['Full-repeat qualification','Startup and supply recovery','Instance queues and private HDL events','Numerical convergence','Device admission']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','source','baseline','out'): p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.source,a.baseline)
    with a.out.open('x') as f: json.dump(result,f,indent=2);f.write('\n')
