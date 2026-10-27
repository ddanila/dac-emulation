#!/usr/bin/env python3
"""Exercise detached children, wait-fork and deferred deletion with native controls."""
import argparse,json,os,platform,shutil,subprocess,tempfile,copy
from pathlib import Path
from ttl7406_probe import sha
from thread_compact_probe import parse_snapshot as parse_threads
from thread_probe import validate_normal
from thread_board_review import queue_snapshot
HERE=Path(__file__).resolve().parent

FIELDS={8:1,9:8,10:2}


def parse_snapshot(lines):
    split=next((i for i,l in enumerate(lines) if l.startswith('VTQ_BEGIN ')),None)
    if split is None:raise ValueError('Missing queue binding')
    t=parse_threads(lines[:split]);q=queue_snapshot(lines[split:])
    if t['tick']!=q['tick']:raise ValueError('Thread/queue time mismatch')
    return dict(threads=t,queue=q)


def validate(snapshot):
    t=snapshot['threads'];validate_normal(t);live={x['id']:x for x in t['threads']};scheduled=set();deleted=set()
    for e in snapshot['queue']['events']:
        identity=e['thread']
        if identity not in live or not e['key']:raise ValueError('Unknown queued thread')
        if e['kind']==2:
            if identity in deleted or live[identity]['state'][8]!='1' or e['region']!='del_thr':raise ValueError('Invalid deferred deletion')
            deleted.add(identity);continue
        while identity:
            if identity in scheduled or identity not in live or live[identity]['state'][7]!='1':raise ValueError('Invalid scheduled chain')
            scheduled.add(identity);identity=live[identity]['wait']
    if scheduled!={i for i,x in live.items() if x['state'][7]=='1'} or scheduled&deleted:raise ValueError('Queue/state disagreement')


def target(snapshot,field):
    return next((i for i,t in enumerate(snapshot['threads']['threads']) if t['state'][FIELDS[field]]=='1' and (field!=9 or t['state'][4]=='1')),None)


def changed_snapshot(before,changed,field):
    i=target(before,field)
    if i is None:raise ValueError('Missing live lifecycle target')
    expected=copy.deepcopy(before);t=expected['threads']['threads'][i];index=FIELDS[field]
    t['state']=t['state'][:index]+'0'+t['state'][index+1:]
    if changed!=expected:raise ValueError('Wrong lifecycle fault or unrelated mutation')


def review(root):
    trajectory=None;output=None;faults={i:0 for i in FIELDS};coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('VT_','VTQ_','VTM_'))]
        controls=[l for l in lines if l.startswith(('VT_','VTQ_','VTM_'))]
        if (root/(mode+'.stderr')).read_text():raise ValueError('Unexpected simulator diagnostics')
        expected=['DEFER_CALLBACK','CHILD_A 2000','DEFER_CALLBACK','CHILD_B 4000','FINISHED 17000']
        if ordinary[:5]!=expected or len(ordinary)!=6 or '$finish called at 17000 (1ps)' not in ordinary[-1]:raise ValueError('Changed/missing lifecycle continuation')
        if output is None:output=ordinary
        elif output!=ordinary:raise ValueError('Changed complete output')
        cursor=0;pointers={};shots=[];previous=set();retired=set();event_bindings={};last_events=set();retired_events=set();addresses={};deleted_ids=set()
        def consume(line):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=line:raise ValueError('Expected '+line)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VTQ_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated snapshot')
            cursor+=1;return parse_snapshot(controls[start:cursor])
        def pointer(p):
            if not p:return 0
            if p not in pointers:pointers[p]=len(pointers)+1
            return pointers[p]
        for stage,tick in enumerate((1000,1000,2000,5000,6000,6000,17000)):
            consume(f'VTM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VTM_BEFORE');before=snapshot();validate(before)
                if before['threads']['tick']!=tick:raise ValueError('Wrong lifecycle boundary')
                consume('VTM_REPEAT')
                if snapshot()!=before:raise ValueError('Observation changed state')
                live={t['id'] for t in before['threads']['threads']}
                if live&retired:raise ValueError('Retired thread identity returned')
                retired.update(previous-live);previous=live
                events=set()
                for e in before['queue']['events']:
                    eid=e['id'];binding=(e['kind'],e['thread'],e['key']);events.add(eid)
                    if eid in retired_events or (eid in event_bindings and event_bindings[eid]!=binding):raise ValueError('Reused/rebound queue event')
                    event_bindings[eid]=binding
                    if e['kind']==2:deleted_ids.add(e['thread']);coverage.add('deletion-queue')
                    if e['key'] in addresses and addresses[e['key']]!=e['thread']:
                        if addresses[e['key']] not in retired:raise ValueError('Aliased live storage')
                        coverage.add('storage-reused-with-fresh-identity')
                    addresses[e['key']]=e['thread']
                retired_events.update(last_events-events);last_events=events
                for t in before['threads']['threads']:
                    if t['state'][1]=='1' and t['parent']:coverage.add('detached')
                    if t['state'][2]=='1':coverage.add('wait-fork')
                    if t['state'][5]=='1' and t['state'][7]=='1':coverage.add('disabled-pending-zombie')
                    if t['state'][8]=='1':coverage.add('deferred-delete')
                if mode=='corrupt':
                    for field in FIELDS:
                        if target(before,field) is None:continue
                        consume(f'VTM_CHANGED {field}');changed_snapshot(before,snapshot(),field)
                        consume('VTM_RESTORED')
                        if snapshot()!=before:raise ValueError('Lifecycle fault not restored')
                        consume(f'VTM_FAULT {field} 1 1');faults[field]+=1
                normalized=copy.deepcopy(before)
                for t in normalized['threads']['threads']:
                    for key in ('pc','scope','writeContext','readContext','event'):t[key]=pointer(t[key])
                    t['objects']=[pointer(p) for p in t['objects']]
                for e in normalized['queue']['events']:e['key']=pointer(e['key'])
                shots.append(normalized)
            consume(f'VTM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Extra lifecycle records')
        if shots:
            if not deleted_ids or not deleted_ids<=retired:raise ValueError('Missing deferred deletion completion')
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Faults changed normal internal trajectory')
    required={'detached','wait-fork','deferred-delete','deletion-queue','disabled-pending-zombie','storage-reused-with-fresh-identity'}
    if not required<=coverage or not all(faults.values()):raise ValueError('Missing lifecycle coverage '+str(required-coverage))
    return dict(completed=True,qualified=False,simulationOutputExactlyEqual=True,normalStateTrajectoryExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,observedStateFamilies=sorted(coverage),scope='Detached children, wait-fork, disabled pending zombie threads, deferred-delete queue binding and completion; restored actual lifecycle flags and fresh identity after storage reuse.',notEstablished=['Board integration and broader operating windows','Freed-storage contents/equivalence','Deep scope/context/code/object referents and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/thread_lifecycle_probe.c' if ext=='c' else 'fixtures/thread_lifecycle_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_THREAD_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('thread_lifecycle_probe.py','thread_probe.py','thread_compact_probe.py','thread_board_review.py','fixtures/thread_lifecycle_probe.c','fixtures/thread_lifecycle_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Thread lifecycle controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
