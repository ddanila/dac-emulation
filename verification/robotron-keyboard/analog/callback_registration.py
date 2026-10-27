#!/usr/bin/env python3
"""Native callback growth, deferred admission and registration during dispatch."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from callback_list_probe import parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());observations=0
    stages=('','A',None,'BA','CBA','CB','CB','','D','D')
    ticks=(1000,1000,2000,3000,5000,6000,7000,8000,9000,10000)
    expected=['S0','REG_NEW_REFUSED','ADMIT A','S1',
      'REG_ACTIVE_REFUSED','CALLBACK 2000 A 1 0','REG_NEW_REFUSED','REG_ACTIVE_AFTER_ADD_REFUSED','S2',
      'ADMIT B','S3','REG_ACTIVE_REFUSED','CALLBACK 4000 B 2 0','REG_ACTIVE_REFUSED','CALLBACK 4000 A 2 0',
      'REG_NEW_REFUSED','ADMIT C','S4','REG_ACTIVE_REFUSED','CALLBACK 6000 C 3 0','REG_ACTIVE_REFUSED','CALLBACK 6000 B 3 0',
      'S5','S6','S7','REG_NEW_REFUSED','ADMIT D','S8','REG_ACTIVE_REFUSED','CALLBACK 10000 D 5 0','S9','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native registration run failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=0;events=[];ids={};rows={};layout=None;callback_owner=None
        def consume(wanted):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=wanted:raise ValueError('Expected '+wanted)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VCL_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated registration image')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if line.startswith('REG_ADMIT '):
                a=line.split();cursor+=1
                if mode!='enabled' or len(a)!=3 or a[1] not in 'ABCD' or a[1] in ids or int(a[2])<=max(ids.values(),default=0):raise ValueError('Reused or invalid callback lifetime')
                ids[a[1]]=int(a[2]);events.append('ADMIT '+a[1]);continue
            if not line.startswith('REG_STAGE '):
                events.append('finish' if '$finish called at 11000 (1ps)' in line else line);cursor+=1;continue
            consume(f'REG_STAGE {stage}');events.append(f'S{stage}')
            if stage>=len(stages):raise ValueError('Extra registration stage')
            if mode=='enabled':
                if stage==2:consume('REG_UNADMITTED_REFUSED')
                else:
                    consume('REG_BEFORE');before=snapshot();consume('REG_REPEAT')
                    if snapshot()!=before or before['tick']!=ticks[stage]:raise ValueError('Changed observation or time')
                    owners=[(o['id'],o['pointer'],o['kind'],o['wordHead'],o['words']) for o in before['owners']]
                    if layout is None:layout=owners
                    if owners!=layout:raise ValueError('Changed owner/association allocation')
                    populated=[o for o in before['owners'] if o['callbacks']]
                    if len(populated)!=bool(stages[stage]):raise ValueError('Wrong callback owner population')
                    callbacks=populated[0]['callbacks'] if populated else []
                    if populated:
                        if callback_owner is None:callback_owner=populated[0]['id']
                        if populated[0]['id']!=callback_owner:raise ValueError('Changed callback owner')
                    if [c['id'] for c in callbacks]!=[ids[label] for label in stages[stage]]:raise ValueError('Wrong ordered callback membership')
                    for label,cb in zip(stages[stage],callbacks):
                        if label not in rows:
                            if not cb['function'] or not cb['object'] or not cb['user']:raise ValueError('Invalid admitted caller fields')
                            rows[label]=copy.deepcopy(cb)
                            if label!='A':
                                if cb['function']!=rows['A']['function'] or cb['object']!=rows['A']['object'] or cb['user']!=rows['A']['user']+ord(label)-ord('A'):raise ValueError('Changed callback identity binding')
                    want=[copy.deepcopy(rows[label]) for label in stages[stage]]
                    for i,cb in enumerate(want):
                        cb['next']=want[i+1]['pointer'] if i+1<len(want) else 0
                        if stage==6 or stage==4 and stages[stage][i]=='A':cb['function']=0
                    if callbacks!=want:raise ValueError('Changed lifecycle fields or deferred deletion')
                    observations+=1
            consume(f'REG_DONE {stage}');stage+=1
        want=expected if mode=='enabled' else [e for e in expected if not e.startswith(('REG_','ADMIT '))]
        if stage!=10 or events!=want:raise ValueError('Changed native registration/dispatch continuation: '+repr(events))
        if mode=='enabled' and set(ids)!=set('ABCD'):raise ValueError('Missing registered lifetimes')
    return dict(qualified=False,controlsPassed=True,observations=observations,originalContinuationExactlyEqual=True,scope='Observe an empty owner list before registration, add an exact-base callback during active native dispatch, and refuse inventory both during traversal and after return until explicit caller handoff. New callbacks run on the next native value change. Preserve ordered growth, cancellation before deletion, empty-list recovery and fresh lifetime IDs after re-registration, with exact original callback values/order.',notEstablished=['Reentrant nested value dispatch and suspended traversal capture','Array-association allocation/removal, typed referents and operational integration','Compact encoding and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/callback_registration.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on')]:
        env=dict(os.environ,K7658_CALLBACK_LISTS=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('callback_registration.py','callback_list_probe.py','net_probe.py','net_types_probe.py','fixtures/callback_registration.c','fixtures/callback_registration.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Native callback registration controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
