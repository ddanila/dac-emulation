#!/usr/bin/env python3
"""Replay restored memory faults that resume ordinary execution."""
import argparse,json
from pathlib import Path
from memory_late_core_review import inventory,port_contract,verify_symbols,logical_sha
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    names=['memory-'+n+'-corrupt' for n in ('name','name-pointer','cache-pointer','port-head','storage-pointer')]
    runs={n:json.loads((root/n/'run.json').read_text()) for n in names};first=runs[names[0]]
    # This existing helper uses its 'off' argument only as a dependency map.
    # Pin symbols to the first fault run; no disabled/transient run is implied.
    identities=verify_symbols(root,{'off':first})
    prior=json.loads((root/'baseline-assessment.json').read_text());baseline=json.loads((root/'baseline/run.json').read_text())
    if not prior['controlsPassed'] or prior['receipts']['off']!=sha(root/'baseline/run.json'):raise ValueError('Unreviewed preflight source')
    compiled=(root/'baseline/io.vvp').read_text();results={}
    for name,r in runs.items():
        folder=root/name
        if not r['completed'] or r.get('error') or not r.get('selectedBoundaries') or r['exitCode']!=0 or r['expectedExitCode']!=0 or r['log']['exitCode']!=0:raise ValueError('Incomplete restored-fault continuation')
        if r['mode']!=name or r['producerSha256']!=sha(HERE/'memory_continue_capture.py'):raise ValueError('Changed preflight producer/mode')
        if r['runtime']!=baseline['runtime'] or r['externalDependencies']!=first['externalDependencies'] or r['inputs']!=first['inputs'] or r['endSeconds']!=baseline['endSeconds']:raise ValueError('Unmatched preflight controls')
        expected=dict(first['environment'],ROBOTRON_PRIVATE_DISPLAY=name)
        if r['environment']!=expected:raise ValueError('Changed preflight environment')
        for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('icarusBuildSha256','icarus-build.json'),('symbolReceiptSha256','symbols.json')]:
            if r[key]!=sha(root/path):raise ValueError('Changed '+key)
        for filename,digest in r['inputs'].items():
            if sha(folder/filename)!=digest:raise ValueError('Changed preflight input')
        if logical_sha(folder/'ngspice.log')!=r['log']['sha256'] or logical_sha(folder/'waveform.raw')!=r['storage']['waveform.raw']['sha256']:raise ValueError('Changed preflight output')
        results[name]=inventory(folder/'ngspice.log',identities,fault_type=name.removesuffix('-corrupt'),contract=port_contract(compiled),compiled=compiled)
    return dict(qualified=False,controlsPassed=True,negativeControls=results,scope='Selected later memory faults, complete snapshot restoration and normal producer exit receipts. Full waveform and firmware continuation comparisons are delegated to memory_continue_review.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with a.out.open('x') as f:json.dump(review(a.root),f,indent=2);f.write('\n')
