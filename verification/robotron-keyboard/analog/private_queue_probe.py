#!/usr/bin/env python3
"""Exercise queued HDL event observation separately from board rollback claims."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
REGIONS=('start','active','inactive','nbassign','rwsync','rosync','del_thr')


def snapshot(lines):
    begin=lines[0].split()
    if len(begin)!=5 or begin[:2]!=['VQ_BEGIN','1'] or begin[3:]!=['1','0']:
        raise ValueError('Invalid running scheduler header')
    now=int(begin[2]);absolute=now;times=[];events={};counts={};types=set()
    if now<0:raise ValueError('Invalid current time')
    for line in lines[1:-1]:
        a=line.split();kind=a[0]
        if kind=='VQ_TIME':
            if len(a)!=4:raise ValueError('Invalid time record')
            index,delay,when=map(int,a[1:])
            if index!=len(times) or delay<0 or when!=absolute+delay:raise ValueError('Invalid time ordering')
            absolute=when;times.append(when)
        elif kind in ('VQ_EVENT','VQ_COUNT'):
            if len(a)!=(6 if kind=='VQ_EVENT' else 4):raise ValueError('Invalid queue record')
            index=int(a[1]);region=a[2];ordinal=int(a[3]);key=(index,region)
            if not ((index==-1 and region in ('init','final')) or (0<=index<len(times) and region in REGIONS)):
                raise ValueError('Unknown queue region')
            if key in counts:raise ValueError('Queue record follows terminal count')
            items=events.setdefault(key,[])
            if ordinal!=len(items):raise ValueError('Missing or reordered event')
            if kind=='VQ_COUNT':counts[key]=ordinal
            else:items.append(a[4:]);types.add(tuple(a[4:]))
        else:raise ValueError('Unknown snapshot record')
    expected={(-1,'init'),(-1,'final')}|{(i,r) for i in range(len(times)) for r in REGIONS}
    if set(counts)!=expected or lines[-1]!=f'VQ_END {len(times)}':raise ValueError('Incomplete queue inventory')
    return {'time':now,'timeSlots':times,'events':sum(counts.values()),'eventTypes':[list(x) for x in sorted(types)]}


def review(root):
    texts={name:(root/(name+'.stdout')).read_text() for name in ('baseline','disabled','enabled','corrupt')}
    base=''.join(l for l in texts['baseline'].splitlines(True) if not l.startswith('VQ_'))
    inventories={};all_types=set()
    for name,text in texts.items():
        if (root/(name+'.stderr')).read_text():raise ValueError('Unexpected runtime diagnostic')
        if ''.join(l for l in text.splitlines(True) if not l.startswith('VQ_'))!=base:
            raise ValueError('Changed timestamped HDL output')
        api=[l for l in text.splitlines() if l.startswith('VQ_API ')]
        if api!=[f'VQ_API {int(name!="baseline")}']*3:raise ValueError('Wrong loaded runtime')
        shots=[];current=[]
        for line in text.splitlines():
            if line.startswith('VQ_API '):continue
            if line.startswith('VQ_BEGIN '):
                if current:raise ValueError('Nested snapshot')
                current=[line]
            elif line.startswith('VQ_'):
                if not current:raise ValueError('Orphan snapshot record')
                current.append(line)
                if line.startswith('VQ_END '):shots.append(current);current=[]
        if current:raise ValueError('Unterminated snapshot')
        stride=2 if name=='enabled' else 3 if name=='corrupt' else 0
        if len(shots)!=3*stride:raise ValueError('Missing control observations')
        measured=[snapshot(s) for s in shots]
        for s in measured:all_types.update(map(tuple,s['eventTypes']))
        for i in range(0,len(shots),stride or 1):
            if stride==2 and shots[i]!=shots[i+1]:raise ValueError('Observer changed queue topology')
            if stride==3 and (shots[i]==shots[i+1] or shots[i]!=shots[i+2]):raise ValueError('Undetected or unrestored fault')
            if measured[i]['time']!=(2000,12000,22000)[i//stride]:raise ValueError('Wrong observation time')
        inventories[name]=measured
    expected={'15vthread_event_s','22assign_vector4_event_s','15generic_event_s'}
    if not expected.issubset({t[0] for t in all_types}):raise ValueError('Missing event-class coverage')
    return {'completed':True,'qualified':False,'timestampedOutputExactlyEqual':True,
            'repeatedSnapshotsExactlyEqual':True,'timeMutationsDetectedAndRestored':3,'inventories':inventories,
            'scope':'Pinned Icarus standalone fixture: ordered queue topology and dynamic event classes only.',
            'notEstablished':['Event payloads and currently executing event','Thread/program-counter serialization','All scheduler regions populated','Board bridge integration and rollback','Freed event storage']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed candidate build')
    for ext in ('c','v'):shutil.copyfile(HERE/f'fixtures/private_queue_probe.{ext}',out/f'probe.{ext}')
    subprocess.run(['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    subprocess.run(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')],check=True)
    libraries={'baseline':str(baseline),'candidate':str(candidate/'vvp/libvvp.so')}
    runtime={p:sha(Path(p)) for p in [*libraries.values(),str(candidate/'vvp/vvp'),*map(str,modules.glob('*.vpi'))]}
    commands={}
    for name,library,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_QUEUE_PROBE=mode)
        env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(library.parent)
        command=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];commands[name]=command
        p=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr);p.check_returncode()
    if any(sha(Path(p))!=h for p,h in runtime.items()):raise ValueError('Changed runtime')
    result=review(out);result.update(runtime=runtime,commands=commands,candidateBuildSha256=sha(candidate/'build.json'),
        sources={n:sha(HERE/n) for n in ('private_queue_probe.py','fixtures/private_queue_probe.c','fixtures/private_queue_probe.v','engine-patches/icarus-queue-observer.patch')})
    shutil.copyfile(candidate/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(out/'assessment.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('candidate','baseline','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        measured=review(a.check);retained=json.loads((a.check/'assessment.json').read_text())
        if any(retained.get(k)!=v for k,v in measured.items()):raise ValueError('Changed retained assessment')
        print('Standalone queue controls verified; no board rollback claim.')
    else:
        if any(x is None for x in (a.candidate,a.baseline,a.modules,a.out)):p.error('Need candidate, baseline, modules and out')
        run(a.candidate,a.baseline,a.modules,a.out)
