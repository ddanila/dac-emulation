#!/usr/bin/env python3
"""Capture and review typed wait-event heads and initialized history."""
import argparse,json,os,platform,shutil,subprocess,tempfile,copy
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def pointer(s):return 0 if s=='(nil)' else int(s,16)

def parse_snapshot(lines):
    from thread_compact_probe import parse_snapshot as threads
    i=next((i for i,l in enumerate(lines) if l.startswith('VT_BEGIN ')),None)
    if i is None:raise ValueError('Missing live-thread inventory')
    wait=lines[:i];a=wait[0].split();z=wait[-1].split()
    if len(a)!=3 or a[:2]!=['VWE_BEGIN','1'] or len(z)!=2 or z[0]!='VWE_END':raise ValueError('Invalid wait framing')
    result=dict(tick=int(a[2]),events=[],threads=threads(lines[i:]));event=None;seen=set()
    for line in wait[1:-1]:
        a=line.split()
        if a[0]=='VWE_EVENT':
            if len(a)!=9:raise ValueError('Invalid wait event')
            identity,kind=int(a[1]),int(a[2]);owner,context=map(pointer,a[3:5]);has_head,thread=map(int,a[5:7]);head,referent=map(pointer,a[7:9])
            if identity<1 or not owner or kind not in (1,2,3,4,11,12,13,14) or has_head not in (0,1) or thread<0 or bool(thread)!=bool(head):raise ValueError('Invalid wait identity')
            if (identity,context) in seen or has_head!=int(kind<10 or context!=0) or (not has_head and thread):raise ValueError('Aliased/missing context head')
            seen.add((identity,context));event=dict(id=identity,kind=kind,owner=owner,context=context,hasHead=has_head,thread=thread,head=head,referent=referent,caches=[])
            result['events'].append(event)
        elif a[0]=='VWE_EDGE':
            if event is None or 'edge' in event or len(a)!=3 or not 0<=int(a[1])<65536 or len(a[2])!=4 or set(a[2])-set('0123'):raise ValueError('Invalid edge cache')
            event['edge']=dict(mask=int(a[1]),bits=a[2])
        elif a[0]=='VWE_CACHE':
            if event is None or len(a)!=5 or int(a[1])!=len(event['caches']):raise ValueError('Invalid cache order')
            kind,size=int(a[2]),int(a[3]);data=a[4]
            if size<0 or kind not in (0,1,2,3):raise ValueError('Invalid cache type')
            if kind==0 and (size!=0 or data!='-'):raise ValueError('Missing cache has payload')
            if kind==1 and ((size==0 and data!='-') or (size>0 and (len(data)!=size or set(data)-set('0123')))):raise ValueError('Invalid vector cache')
            if kind in (2,3):
                if kind==2 and size!=64:raise ValueError('Invalid real width')
                n=16 if kind==2 else size*2
                if (not n and data!='-') or (n and (len(data)!=n or set(data)-set('0123456789abcdef'))):raise ValueError('Invalid exact cache bytes')
            event['caches'].append(dict(kind=kind,size=size,data=data))
        else:raise ValueError('Unknown event record')
    if len(result['events'])!=int(z[1]) or result['tick']<0 or result['tick']!=result['threads']['tick']:raise ValueError('Wait/thread time or count mismatch')
    for event in result['events']:
        k=event['kind']%10
        if ('edge' in event)!=(k==1) or len(event['caches'])!=(4 if k==2 else 0):raise ValueError('Incomplete typed state')
    return result


def validate(snapshot):
    from thread_probe import validate_normal
    validate_normal(snapshot['threads'])
    live={t['id']:t for t in snapshot['threads']['threads']};waiting=set();owners={}
    for e in snapshot['events']:
        binding=(e['kind'],e['owner'],e['referent'])
        if e['id'] in owners and owners[e['id']]!=binding:raise ValueError('Changed wait owner')
        owners[e['id']]=binding
        t=e['thread']
        while t:
            if t in waiting or t not in live or live[t]['state'][6]!='1':raise ValueError('Invalid or multiply owned waiter')
            waiting.add(t);t=live[t]['wait']
    if waiting!={i for i,t in live.items() if t['state'][6]=='1'}:raise ValueError('Missing event ownership')


def changed_snapshot(before,after,field):
    expected=copy.deepcopy(before)
    for e in expected['events']:
        if field==0 and e['thread']:e.update(thread=0,head=0);break
        if field==1 and 'edge' in e:e['edge']['mask']^=1;break
        if field==2 and 'edge' in e:e['edge']['bits']=str(int(e['edge']['bits'][0])^1)+e['edge']['bits'][1:];break
        if field==3:
            target=next((c for c in e['caches'] if c['kind']==1 and c['size']),None)
            if target:target['data']=str(int(target['data'][0])^1)+target['data'][1:];break
    else:raise ValueError('Missing fault target')
    if expected!=after:raise ValueError('Wrong wait-event fault or unrelated mutation')


def review(root):
    faults={i:0 for i in range(4)};reference=None;trajectory=None;coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        controls=[l for l in lines if l.startswith(('VWM_','VWE_','VT_'))]
        ordinary=[l for l in lines if not l.startswith(('VWM_','VWE_','VT_'))]
        if (root/(mode+'.stderr')).read_text():raise ValueError('Unexpected simulator diagnostics')
        if reference is None:reference=ordinary
        elif ordinary!=reference:raise ValueError('Changed complete fixture output')
        if not all(any(l.startswith(p) for l in ordinary) for p in ('AUTO_EDGE 2000','AUTO_ANY 2000','AUTO_NAMED 4000','NAMED 4000','RISE 6000','BUS 6000')):raise ValueError('Missing fixture continuation')
        cursor=0;shots=[];pointers={}
        def consume(s):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=s:raise ValueError('Expected '+s)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VT_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated snapshot')
            cursor+=1;return parse_snapshot(controls[start:cursor])
        def canonical(p):
            if not p:return 0
            if p not in pointers:pointers[p]=len(pointers)+1
            return pointers[p]
        for stage,tick in enumerate((1000,3000,5000,7000)):
            consume(f'VWM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VWM_BEFORE');before=snapshot();validate(before)
                if before['tick']!=tick:raise ValueError('Wrong observation time')
                for kind in (11,12,13,14):
                    instances=[e for e in before['events'] if e['kind']==kind and e['context']]
                    if len(instances)!=(2 if stage<2 else 0):raise ValueError('Missing automatic context creation/release coverage')
                consume('VWM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                for e in before['events']:
                    coverage.add('kind-'+str(e['kind']))
                    if e['hasHead']:coverage.add('waiting' if e['thread'] else 'empty')
                    for c in e['caches']:coverage.add('cache-'+str(c['kind']))
                if mode=='corrupt':
                    for field in range(4):
                        consume(f'VWM_CHANGED {field}');changed_snapshot(before,snapshot(),field)
                        consume('VWM_RESTORED')
                        if snapshot()!=before:raise ValueError('Wait fault not restored')
                        consume(f'VWM_FAULT {field} 1 1');faults[field]+=1
                normalized=copy.deepcopy(before)
                for e in normalized['events']:
                    for key in ('owner','context','head','referent'):e[key]=canonical(e[key])
                for t in normalized['threads']['threads']:
                    for key in ('pc','scope','writeContext','readContext','event'):t[key]=canonical(t[key])
                    t['objects']=[canonical(p) for p in t['objects']]
                shots.append(normalized)
            consume(f'VWM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Extra control records')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Faults changed normal internal trajectory')
    required={'kind-1','kind-2','kind-3','kind-4','kind-11','kind-12','kind-13','kind-14','cache-0','cache-1','cache-2','cache-3','waiting','empty'}
    if not required<=coverage or not all(faults.values()):raise ValueError('Missing event coverage '+str(required-coverage))
    return dict(completed=True,qualified=False,simulationOutputExactlyEqual=True,normalStateTrajectoryExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,observedStateFamilies=sorted(coverage),scope='Typed wait heads and initialized event histories with live-thread ownership; static and automatic edge/anyedge/named events and static/automatic event-or; restored native field faults.',notEstablished=['Board integration','Context reuse/lifetime proof','Nonempty event-controlled assignment payloads','Deep code/scope/context/object/fanout referents, freed storage and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/wait_probe.c' if ext=='c' else 'fixtures/wait_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_WAIT_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('wait_probe.py','fixtures/wait_probe.c','fixtures/wait_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Wait-event controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
