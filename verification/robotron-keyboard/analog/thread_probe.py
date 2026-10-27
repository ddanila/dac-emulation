#!/usr/bin/env python3
"""Exercise initialized live-thread observation and restored runtime mutations."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def parse_snapshot(lines):
    cursor=0
    def take(name,count=None):
        nonlocal cursor
        if cursor>=len(lines):raise ValueError('Truncated thread snapshot')
        a=lines[cursor].split();cursor+=1
        if not a or a[0]!=name or (count is not None and len(a)!=count):raise ValueError('Missing thread record: '+name)
        return a
    ptr=lambda x:0 if x=='(nil)' else int(x,16)
    a=take('VT_BEGIN',4)
    if a[1]!='1':raise ValueError('Unknown thread format')
    tick,running=map(int,a[2:]);threads=[]
    while cursor<len(lines) and lines[cursor].startswith('VT_THREAD '):
        a=take('VT_THREAD',10);identity=int(a[1]);parent,wait=map(int,a[4:6]);count=int(a[9])
        item=dict(id=identity,pc=ptr(a[2]),scope=ptr(a[3]),parent=parent,wait=wait,writeContext=ptr(a[6]),readContext=ptr(a[7]),event=ptr(a[8]),eventCount=count)
        if identity<1 or min(parent,wait,count)<0:raise ValueError('Invalid thread identity')
        state=take('VT_STATE',2)[1]
        if len(state)!=9 or any(c not in '01' for c in state):raise ValueError('Invalid lifecycle flags')
        a=take('VT_FLAGS',3);flags=a[2]
        if a[1]!='512' or len(flags)!=512 or any(c not in '-0123' for c in flags):raise ValueError('Invalid initialized flag vector')
        a=take('VT_WORDS',18)
        if a[1]!='16' or any(v!='-' and (len(v)!=16 or any(c not in '0123456789abcdef' for c in v)) for v in a[2:]):raise ValueError('Invalid initialized word vector')
        item.update(state=state,flags=flags,words=a[2:],children=[],args=[],vectors=[],reals=[],strings=[],objects=[])
        for kind,groups in [('VT_CHILDREN',2),('VT_ARGS',3)]:
            for group in range(groups):
                a=take(kind)
                if len(a)<3 or int(a[1])!=group or int(a[2])!=len(a)-3:raise ValueError('Invalid thread relationship/argument array')
                values=list(map(int,a[3:]))
                if any(v<0 for v in values) or (kind=='VT_CHILDREN' and (any(v<1 for v in values) or sorted(set(values))!=values)):raise ValueError('Invalid relationship/argument value')
                item['children' if kind=='VT_CHILDREN' else 'args'].append(values)
        counts=list(map(int,take('VT_STACKS',5)[1:]))
        if min(counts)<0 or counts[3]>32:raise ValueError('Invalid live stack lengths')
        for _ in range(counts[0]):
            a=take('VT_VEC',3);size=int(a[1]);bits=a[2]
            if size<0 or (not size and bits!='-') or (size and (len(bits)!=size or any(c not in '0123' for c in bits))):raise ValueError('Invalid logical stack vector')
            item['vectors'].append(dict(size=size,bits=bits))
        for _ in range(counts[1]):
            bits=take('VT_REAL',2)[1]
            if len(bits)!=16 or any(c not in '0123456789abcdef' for c in bits):raise ValueError('Invalid real representation')
            item['reals'].append(bits)
        for _ in range(counts[2]):
            a=take('VT_STRING',3);size=int(a[1]);bits=a[2]
            if size<0 or (not size and bits!='-') or (size and (len(bits)!=size*2 or any(c not in '0123456789abcdef' for c in bits))):raise ValueError('Invalid initialized string')
            item['strings'].append('' if bits=='-' else bits)
        for _ in range(counts[3]):item['objects'].append(ptr(take('VT_OBJECT',2)[1]))
        a=take('VT_SOURCE',3);line=int(a[1]);filename=a[2]
        if line<0 or (filename!='-' and (len(filename)%2 or any(c not in '0123456789abcdef' for c in filename))):raise ValueError('Invalid source location')
        item['source']=dict(line=line,file=filename);threads.append(item)
    a=take('VT_END',2)
    if cursor!=len(lines) or int(a[1])!=len(threads) or min(tick,running)<0 or len({t['id'] for t in threads})!=len(threads):raise ValueError('Invalid thread footer')
    return dict(tick=tick,running=running,threads=threads)


def validate_normal(snapshot):
    threads={t['id']:t for t in snapshot['threads']}
    if snapshot['running'] and snapshot['running'] not in threads:raise ValueError('Unknown running thread')
    for identity,t in threads.items():
        if not t['pc'] or not t['scope'] or t['flags'][:4]!='0132':raise ValueError('Invalid live thread PC/scope/constants')
        if t['parent'] and t['parent'] not in threads:raise ValueError('Unknown parent')
        for group,children in enumerate(t['children']):
            for child in children:
                if child not in threads or threads[child]['parent']!=identity or int(threads[child]['state'][1])!=group:raise ValueError('Broken parent/child relation')
        visited=set();current=identity
        while current:
            if current in visited or current not in threads:raise ValueError('Cyclic/unknown wait link')
            visited.add(current);current=threads[current]['wait']


def target(snapshot,field):
    for i,t in enumerate(snapshot['threads']):
        if field==0:return ('threads',i,'state')
        if field==1 and any(c!='-' for c in t['flags']):return ('threads',i,'flags')
        if field==2:
            for j,v in enumerate(t['words']):
                if v!='-':return ('threads',i,'words',j)
        if field==3:return ('threads',i,'pc')
        if field==4:return ('threads',i,'wait')
        if field==5 and t['vectors'] and t['vectors'][0]['size']:return ('threads',i,'vectors',0,'bits')
        if field==6 and t['reals']:return ('threads',i,'reals',0)
        if field==7 and t['strings']:return ('threads',i,'strings',0)
    return None


def changed_snapshot(before,changed,field):
    from island_probe import differences
    path=target(before,field)
    if path is None or differences(before,changed)!=[path]:raise ValueError('Wrong thread fault or unrelated mutation')
    a,b=before,changed
    for key in path:a=a[key];b=b[key]
    if field==0:expected=a[:7]+str(1-int(a[7]))+a[8:]
    elif field==1:
        index=next(i for i,c in enumerate(a) if c!='-');expected=a[:index]+('0' if a[index]=='1' else '1')+a[index+1:]
    elif field in (2,6):expected=format(int(a,16)^1,'016x')
    elif field==3:expected=0
    elif field==4:expected=0 if a else before['threads'][path[1]]['id']
    elif field==5:expected=('0' if a[0]=='1' else '1')+a[1:]
    else:expected=a+'41'
    if b!=expected:raise ValueError('Wrong thread field change')


def review(root):
    expected=['STEP 2000 0 1','BRANCH 0','STEP 3000 1 0','BRANCH 1','STEP 4000 2 1',
              'RESULT 4000 58.25','VALUES ffffffffffffffffffff keptarg','WAKE 4000','CHILD_A 6000','CHILD_B 7000']
    times=[1000,2000,3000,4000,4000,4000,4000,5000,5000,7000]
    output=None;trajectory=None;faults={i:0 for i in range(8)}
    coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        if (root/(mode+'.stderr')).read_text():raise ValueError('Simulator diagnostic/uninitialized native read')
        lines=(root/(mode+'.stdout')).read_text().splitlines();normal=[l for l in lines if not l.startswith(('VT_','VTM_'))]
        if normal[:-1]!=expected or '$finish called at 8000 (1ps)' not in normal[-1]:raise ValueError('Wrong fixture continuation')
        if output is None:output=normal
        elif normal!=output:raise ValueError('Changed complete simulator output')
        controls=[l for l in lines if l.startswith(('VT_','VTM_'))];cursor=0;snapshots=[];pointers={};previous=set();retired=set();seen={}
        def consume(line):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=line:raise ValueError('Missing/reordered thread control: '+line)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VT_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated thread inventory')
            cursor+=1;return parse_snapshot(controls[start:cursor])
        def pointer(n):
            if not n:return 0
            if n not in pointers:pointers[n]=len(pointers)+1
            return pointers[n]
        for stage,tick in enumerate(times):
            consume(f'VTM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VTM_BEFORE');before=snapshot();validate_normal(before)
                if before['tick']!=tick or not before['running']:raise ValueError('Missing active fixture observation')
                if stage==0 and any(t['flags'][8:]!='-'*504 or t['words']!=['-']*16 for t in before['threads']):raise ValueError('Unwritten storage presented as initialized')
                current={t['id'] for t in before['threads']}
                if current&retired:raise ValueError('Reused thread lifetime')
                retired.update(previous-current);previous=current
                for t in before['threads']:
                    if t['id'] in seen:
                        old=seen[t['id']]
                        if old['scope']!=t['scope'] or any(a!='-' and b=='-' for a,b in zip(old['flags'],t['flags'])) or any(a!='-' and b=='-' for a,b in zip(old['words'],t['words'])):raise ValueError('Changed scope or lost initialized registers')
                    seen[t['id']]=t
                    if t['state'][6]=='1':coverage.add('event-wait')
                    if t['state'][0]=='1' and t['children'][0]:coverage.add('join')
                    if t['state'][7]=='1':coverage.add('scheduled')
                    if t['state'][3]=='1':coverage.add('function')
                    if any(c!='-' for c in t['flags'][8:]):coverage.add('extended-flags')
                    if any(v!='-' for v in t['words']):coverage.add('word-registers')
                    for name in ('vectors','reals','strings'):
                        if t[name]:coverage.add(name)
                consume('VTM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed thread state')
                normalized=copy.deepcopy(before)
                for t in normalized['threads']:
                    for key in ('pc','scope','writeContext','readContext','event'):t[key]=pointer(t[key])
                    t['objects']=[pointer(n) for n in t['objects']]
                snapshots.append(normalized)
                if mode=='corrupt':
                    for field in range(8):
                        if target(before,field) is None:continue
                        consume(f'VTM_CHANGED {field}');changed_snapshot(before,snapshot(),field)
                        consume('VTM_RESTORED')
                        if snapshot()!=before:raise ValueError('Thread fault not restored')
                        consume(f'VTM_FAULT {field} 1 1');faults[field]+=1
            consume(f'VTM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Extra thread control records')
        if snapshots:
            if not retired:raise ValueError('Missing thread destruction')
            if trajectory is None:trajectory=snapshots
            elif trajectory!=snapshots:raise ValueError('Faults changed normal thread trajectory')
    required={'event-wait','join','scheduled','function','extended-flags','word-registers','vectors','reals','strings'}
    if not all(faults.values()) or coverage!=required:raise ValueError('Missing thread state/fault coverage: '+str(required-coverage))
    return dict(completed=True,qualified=False,simulationOutputExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,
                observedStateFamilies=sorted(coverage),scope='Initialized live-thread flags/words, lifecycle and wait/parent/child relationships, and logical vector/real/string stacks; restored mutations with unchanged complete fixture output.',
                notEstablished=['Board integration and queued/wait-event binding','Code/scope/context/object referent contents','Detached/delayed-deletion coverage','Freed-storage equivalence and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/thread_probe.{ext}',out/f'probe.{ext}')
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
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('thread_probe.py','fixtures/thread_probe.c','fixtures/thread_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Initialized live-thread controls verified; board and referent coverage remain open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
