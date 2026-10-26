#!/usr/bin/env python3
"""Review actual recovery coverage separately from complete waveform comparisons."""
import argparse,json,math
from pathlib import Path
from audit_log import records,equal
from output_breakpoint_capture import VARIANTS
from postreset_state_review import stream_info
from raw_pair_review import compare_raw
from staged_output_review import runtime_summary
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def branches(lines,mode):
    if mode not in VARIANTS:raise ValueError('Unknown mode')
    attempts=initial=recoveries=injections=0;active=None;previous=None
    for line in lines:
        a=line.split()
        if len(a)!=8 or a[0]!='OUTPUT_BKPT':raise ValueError('Malformed output breakpoint record')
        fields=[part.split('=',1) for part in a[1:]]
        if any(len(p)!=2 for p in fields):raise ValueError('Malformed field')
        d=dict(fields)
        if set(d)!={'recovery','time','vtime','requested','last','status','injected'}:raise ValueError('Missing or duplicated field')
        phase,status,inject=(int(d[k]) for k in ('recovery','status','injected'))
        t,v,when,last=(float.fromhex(d[k]) for k in ('time','vtime','requested','last'))
        if any(x not in (0,1) for x in (phase,status,inject)) or not all(map(math.isfinite,(t,v,when,last))) or v>=t or last>t:
            raise ValueError('Invalid branch observation')
        if mode=='off' or (inject and (mode!='fail-once' or phase or not status)):raise ValueError('Unexpected injection or disabled telemetry')
        attempts+=1;injections+=inject
        if injections>1:raise ValueError('Repeated injected failure')
        if phase==0:
            if active is not None:raise ValueError('Unfinished recovery')
            initial+=1
            if status:active=(t,v,last);previous=None
        else:
            if active!=(t,v,last) or (previous is not None and when<=previous):raise ValueError('Orphan or nonadvancing recovery')
            recoveries+=1;previous=when
            if not status:active=None
    if active is not None:raise ValueError('Truncated recovery')
    return {'initialRequests':initial,'recoveryRequests':recoveries,'injectedFailures':injections,
            'branchExercised':initial>0,'injectionExercised':injections==1}


def assess(root,source):
    base=json.loads((source/'run.json').read_text());build=json.loads((root/'build.json').read_text())
    if base['exitCode']!=0:raise ValueError('Incomplete baseline')
    receipts={mode:json.loads((root/mode/'run.json').read_text()) for mode in VARIANTS}
    runtime=receipts['off']['runtime'];summaries={};coverage={}
    if runtime['executable']!=base['runtime']['executable']:raise ValueError('Changed simulator')
    old,new=base['runtime']['codeModels'],runtime['codeModels']
    if len(old)!=len(new):raise ValueError('Changed code-model inventory')
    for a,b in zip(old,new):
        if Path(a['path']).name=='digital.cm':
            if Path(b['path']).name!='digital.cm' or b['sha256']!=build['outputs']['digital.cm']:raise ValueError('Wrong candidate model')
        elif a!=b:raise ValueError('Changed unrelated model')
    for mode,folder,r in [('baseline',source,base),*((m,root/m,r) for m,r in receipts.items())]:
        if r['exitCode']!=0 or r['inputs']!=base['inputs']:raise ValueError('Incomplete or changed control')
        if mode!='baseline':
            if r['runtime']!=runtime or r['candidateBuildSha256']!=sha(root/'build.json') or r['sourceRunSha256']!=sha(source/'run.json'):raise ValueError('Changed provenance')
            if r['externalDependencies']!=base['externalDependencies'] or r['environment']!=dict(base['environment'],**VARIANTS[mode]):raise ValueError('Changed conditions')
            if r['variantControllerSha256']!=sha(HERE/'output_breakpoint_capture.py') or r['runnerSha256']!=sha(HERE/'output_history_capture.py'):raise ValueError('Changed capture source')
        for name,digest in r['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed input')
        if set(r['storage'])!={'waveform.raw','ngspice.log'}:raise ValueError('Missing complete streams')
        for name,item in r['storage'].items():
            if stream_info(folder/name)!=item:raise ValueError('Changed stream')
        summary=runtime_summary(folder/'ngspice.log')
        if summary['count'] is None or summary['diagnostic'] or summary['sorry']:raise ValueError('Incomplete or failed run')
        summaries[mode]=summary
        if mode!='baseline':coverage[mode]=branches(records(folder/'ngspice.log',('OUTPUT_BKPT',)),mode)
    comparisons={};firmware={}
    for name,a,b,exact in [('disabledBaseline',source,root/'off',True),('observer',root/'off',root/'observe',True),('forcedFailure',root/'off',root/'fail-once',False)]:
        left='baseline' if a==source else 'off';right=b.name
        comparisons[name]=compare_raw(a/'waveform.raw',b/'waveform.raw',[summaries[left]['count'],summaries[right]['count']],20e-6,exact=exact)
        firmware[name]=equal(a/'ngspice.log',b/'ngspice.log',('FIRST_FETCH ','BUS_','SERIAL_'))
        if exact and not firmware[name]:raise ValueError('Observer changed firmware')
    return {'completed':True,'qualified':False,'coverage':coverage,'comparisons':comparisons,'firmwareEqual':firmware,
            'recoveryControlExercised':coverage['observe']['branchExercised'] and coverage['fail-once']['injectionExercised'],
            'scope':'Complete 20-us fixture. Zero branch activity does not test recovery; waveform differences under injection are measured, not waived. No private HDL rollback or board qualification.',
            'receipts':{m:sha(root/m/'run.json') for m in VARIANTS},'baselineReceiptSha256':sha(source/'run.json'),
            'sources':{n:sha(HERE/n) for n in ('output_breakpoint_review.py','output_breakpoint_capture.py','build_output_breakpoint_probe.py','raw_pair_review.py','audit_log.py','staged_output_review.py','postreset_state_review.py')}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','source','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=assess(a.root,a.source)
    with a.out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
