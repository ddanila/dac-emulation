#!/usr/bin/env python3
"""Review completed drain refinement levels without replacing the full campaign."""
import argparse,json
from pathlib import Path
from postreset_drain_review import validate,experiment,inspect_log,END,FIRMWARE,voltage_gate,compare_raw,logical_sha,equal,HERE
from ttl7406_probe import sha
from cached_net_board_review import sources


def assess(source,folders):
    pinned=sources();base=json.loads((source/'run.json').read_text());base_sha=sha(source/'run.json')
    if base_sha!=sha(HERE/'reports/postreset-adc/25/run.json'):raise ValueError('Changed original baseline')
    if set(folders)!={'coarse','fine','finest'}:raise ValueError('Missing refinement level')
    coarse=folders['coarse'];control=json.loads((coarse/'run.json').read_text())
    build_sha=sha(coarse/'candidate-build.json');bounded_sha=sha(coarse/'bounded-assessment.json')
    if bounded_sha!=sha(HERE/'reports/output-drain-board/assessment.json'):raise ValueError('Changed bounded qualification')
    build=json.loads((coarse/'candidate-build.json').read_text())
    def vpi(run):
        found=[d for d in run['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
        if len(found)!=1:raise ValueError('Ambiguous VPI dependency')
        return found[0]
    old,new=vpi(base),vpi(control)
    if old==new or new['sha256']!=build['outputs']['ivlng.vpi']:raise ValueError('Missing candidate build')
    deps=sorted([new if d==old else d for d in base['externalDependencies']],key=lambda d:d['path'])
    for name,digest in base['inputs'].items():
        if sha(source/name)!=digest:raise ValueError('Changed baseline input')
    scans={};receipts={}
    for label,step in [('coarse',25),('fine',12.5),('finest',6.25)]:
        folder=folders[label];r=json.loads((folder/'run.json').read_text());receipts[label]=sha(folder/'run.json')
        validate(r,base,'on',step,base_sha,build_sha,bounded_sha)
        if sha(folder/'candidate-build.json')!=build_sha or sha(folder/'bounded-assessment.json')!=bounded_sha:raise ValueError('Changed build/control')
        deck,env=experiment((source/'io.cir').read_text(),base['environment'],old['path'],new['path'],'on',step)
        if (folder/'io.cir').read_text()!=deck or r['environment']!=env or r['externalDependencies']!=deps:raise ValueError('Unmatched experiment')
        for name,digest in r['inputs'].items():
            if sha(folder/name)!=digest or (name!='io.cir' and digest!=base['inputs'][name]):raise ValueError('Changed capture input')
        for name,digest in [('ngspice.log',r['log']['sha256']),('waveform.raw',r['storage']['waveform.raw']['sha256'])]:
            if logical_sha(folder/name)!=digest:raise ValueError('Changed capture output')
        scans[label]=inspect_log(folder/'ngspice.log','combined')
    comparisons={};firmware={}
    for label,left,right in [('coarseFine','coarse','fine'),('fineFinest','fine','finest')]:
        comparisons[label]=compare_raw(folders[left]/'waveform.raw',folders[right]/'waveform.raw',[scans[n]['count'] for n in (left,right)],END)
        firmware[label]=equal(folders[left]/'ngspice.log',folders[right]/'ngspice.log',FIRMWARE)
    gate=voltage_gate(comparisons['coarseFine'],comparisons['fineFinest'])
    if sources()!=pinned or any(sha(folders[n]/'run.json')!=h for n,h in receipts.items()):raise ValueError('Changed diagnostic sources or receipts')
    return dict(completed=True,qualified=False,fullCampaignAccepted=False,
        refinementGatePassed=gate['passed'] and all(firmware.values()),voltageGate=gate,
        comparisons=comparisons,firmwareRecordsExactlyEqual=firmware,logs=scans,receipts=receipts,
        baselineReceiptSha256=base_sha,sources=pinned,
        scope='Independent full-window 1.16-ms comparison of the three completed output-drain refinements at 25, 12.5 and 6.25 ns, using unchanged absolute-time 10-mV/non-growth checks and exact firmware records. Does not replace the full campaign: disabled, exact-tick, output-drain and forced-retry effects remain subject to its original reviewer. No full-repeat, supply recovery, complete private rollback or device applicability claim.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','coarse','fine','finest','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();r=assess(a.source,{n:getattr(a,n) for n in ('coarse','fine','finest')});a.out.write_text(json.dumps(r,indent=2)+'\n')
