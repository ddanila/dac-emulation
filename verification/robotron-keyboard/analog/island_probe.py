#!/usr/bin/env python3
"""Capture live island caches/topology and restored faults on the pinned runtime."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def parse_snapshot(lines):
    header=lines[0].split();footer=lines[-1].split()
    if len(header)!=3 or header[:2]!=['VI_BEGIN','1'] or len(footer)!=2 or footer[0]!='VI_END':raise ValueError('Invalid island framing')
    tick=int(header[2]);islands=[];i=1
    if tick<0:raise ValueError('Negative time')
    pointer=lambda s:0 if s=='(nil)' else int(s,16)
    while i<len(lines)-1:
        a=lines[i].split();i+=1
        if len(a)!=7 or a[0]!='VI_ISLAND':raise ValueError('Missing island')
        identity=int(a[1]);flag,head,nb,np=map(int,a[3:])
        if identity<1 or flag not in (0,1) or min(head,nb,np)<0 or head>nb:raise ValueError('Invalid island metadata')
        island=dict(id=identity,key=pointer(a[2]),flag=flag,head=head,ports=[],branches=[])
        for index in range(1,np+1):
            a=lines[i].split();i+=1
            if len(a)!=5 or a[:2]!=['VI_PORT',str(index)]:raise ValueError('Invalid port ordering')
            port=dict(id=index,net=pointer(a[2]),functor=pointer(a[3]),filter=pointer(a[4]),vectors={})
            for name in ('in','out','scratch'):
                a=lines[i].split();i+=1
                if len(a)!=4 or a[:2]!=['VI_VECTOR',name]:raise ValueError('Missing initialized port vector')
                size=int(a[2]);bits=a[3]
                if size<0 or (size==0 and bits!='-') or (size and (len(bits)!=3*size or any(c not in '0123' for c in bits[::3]) or any(c not in '01234567' for c in bits[1::3]+bits[2::3]))):raise ValueError('Invalid strength vector')
                port['vectors'][name]=dict(size=size,bits=bits)
            island['ports'].append(port)
        for index in range(1,nb+1):
            a=lines[i].split();i+=1
            if len(a)!=9 or a[:2]!=['VI_BRANCH',str(index)]:raise ValueError('Invalid branch ordering')
            values=list(map(int,a[2:]));n,pa,pb,la,sa,lb,sb=values
            if not 0<=n<=nb or not all(1<=p<=np for p in (pa,pb)) or not all(1<=v<=nb for v in (la,lb)) or sa not in (0,1) or sb not in (0,1):raise ValueError('Invalid mesh references')
            a=lines[i].split();i+=1
            if len(a)!=8 or a[0]!='VI_TRAN':raise ValueError('Missing transmission gate')
            width,part,offset,active,resistive,state=map(int,a[2:])
            if min(width,part,offset)<0 or active not in (0,1) or resistive not in (0,1) or state not in (0,1,2):raise ValueError('Invalid gate state')
            island['branches'].append(dict(id=index,next=n,a=pa,b=pb,links=[[la,sa],[lb,sb]],enable=pointer(a[1]),width=width,part=part,offset=offset,active=active,resistive=resistive,state=state))
        islands.append(island)
    if i!=len(lines)-1 or len(islands)!=int(footer[1]) or len({x['id'] for x in islands})!=len(islands):raise ValueError('Incomplete/aliased island inventory')
    return dict(tick=tick,islands=islands)


def validate_normal(snapshot):
    for island in snapshot['islands']:
        ports={p['id']:p for p in island['ports']};branches={b['id']:b for b in island['branches']}
        if not island['key'] or len({p['net'] for p in ports.values()})!=len(ports):raise ValueError('Missing/aliased island identity')
        for p in ports.values():
            if not p['net'] or not p['functor']:raise ValueError('Missing port referent')
        order=set();cur=island['head']
        while cur:
            if cur in order:raise ValueError('Cyclic branch list')
            order.add(cur);cur=branches[cur]['next']
        if order!=set(branches):raise ValueError('Unreachable branch')
        for b in branches.values():
            if b['enable'] and b['enable'] not in {p['net'] for p in ports.values()}:raise ValueError('Missing enable-only port')
            for side in (0,1):
                start=(b['id'],side);cur=start;seen=set();port=b['a' if side==0 else 'b']
                while cur not in seen:
                    seen.add(cur);branch=branches[cur[0]]
                    if branch['a' if cur[1]==0 else 'b']!=port:raise ValueError('Mesh joins different ports')
                    cur=tuple(branch['links'][cur[1]])
                if cur!=start:raise ValueError('Mesh cycle does not return to endpoint')


def differences(a,b,path=()):
    if type(a)!=type(b):return [path]
    if isinstance(a,dict):
        if a.keys()!=b.keys():return [path]
        return [p for k in a for p in differences(a[k],b[k],path+(k,))]
    if isinstance(a,list):
        if len(a)!=len(b):return [path]
        return [p for i in range(len(a)) for p in differences(a[i],b[i],path+(i,))]
    return [] if a==b else [path]


def changed_snapshot(before,changed,field):
    candidates=[]
    for i,island in enumerate(before['islands']):
        if field==0:candidates.append(('islands',i,'flag'))
        elif field in (4,5):
            for j,b in enumerate(island['branches']):
                candidates.append(('islands',i,'branches',j,'state') if field==4 else ('islands',i,'branches',j,'links',0,1))
        else:
            name='out' if field==2 else 'in'
            for j,p in enumerate(island['ports']):
                if p['vectors'][name]['size']:candidates.append(('islands',i,'ports',j,'vectors',name,'bits'))
    if not candidates or differences(before,changed)!=[candidates[0]]:raise ValueError('Wrong island fault or unrelated state changed')
    a,b=before,changed
    for key in candidates[0]:a=a[key];b=b[key]
    if field in (0,5):expected=a^1
    elif field==4:expected=0 if a==1 else 1
    elif field==3:
        # Scalar construction normalizes unused strength according to its value.
        value,s0,s1=map(int,a[:3]);s0^=1;s1^=1
        if value==0:s1=s0
        elif value==1:s0=s1
        elif value==2:s0=s1=0
        expected=str(value)+str(s0)+str(s1)+a[3:]
    else:expected=('0' if a[0]=='1' else '1')+'66'+a[3:]
    if b!=expected:raise ValueError('Wrong primitive field mutation')


def canonical(snapshot):
    import copy
    result=copy.deepcopy(snapshot);pointers={}
    def ptr(n):
        if not n:return 0
        if n not in pointers:pointers[n]=len(pointers)+1
        return pointers[n]
    for island in result['islands']:
        island['key']=ptr(island['key'])
        for port in island['ports']:
            for key in ('net','functor','filter'):port[key]=ptr(port[key])
        for branch in island['branches']:branch['enable']=ptr(branch['enable'])
    return result


def fixture_state(snapshot,stage):
    if len(snapshot['islands'])!=1:raise ValueError('Wrong fixture island scope')
    island=snapshot['islands'][0]
    if len(island['branches'])!=1 or len(island['ports'])!=3:raise ValueError('Wrong fixture mesh scope')
    b=island['branches'][0];ports={p['id']:p for p in island['ports']}
    if (b['width'],b['part'],b['offset'],b['active'],b['resistive'])!=(0,0,0,1,0):raise ValueError('Wrong gate parameters')
    a=ports[b['a']];right=ports[b['b']]
    logical=lambda v:''.join('01zx'[int(c)] for c in v['bits'][::3])[::-1] if v['size'] else ''
    expected=[('1010','zzzz','1010','zzzz',0),('1010','zzzz','1010','1010',1),
              ('1010','0101','1010','1010',1),('1010','0101','1010','xxxx',2),
              ('zzzz','0101','xxxx','0101',2),('zzzz','0101','zzzz','0101',0),
              ('1100','0101','1100','1100',1)][stage]
    actual=tuple(logical(v) for v in (a['vectors']['in'],right['vectors']['in'],a['vectors']['out'],right['vectors']['out']))+(b['state'],)
    if actual!=expected:raise ValueError('Cached input/output differs from fixture stimulus/resolution')
    enable=next(p for p in ports.values() if p['net']==b['enable'])
    want=('0000','1111','1111','xxxx','xxxx','0000','1111')[stage]
    if logical(enable['vectors']['in'])!=want or enable['vectors']['out']['size']:raise ValueError('Wrong enable-only import state')
    if island['flag'] or any(p['vectors']['scratch']['size'] for p in ports.values()):raise ValueError('Unconsumed fixture resolution')
    stable=copy.deepcopy(snapshot);stable.pop('tick')
    for item in stable['islands']:
        item.pop('flag')
        for port in item['ports']:port.pop('vectors')
        for branch in item['branches']:branch.pop('state')
    return stable


def review(root):
    expected=['CHANGE 0 0 1010 zzzz','CHANGE 1000 1 1010 1010','CHANGE 3000 x 1010 xxxx',
              'CHANGE 4000 x xxxx 0101','CHANGE 5000 0 zzzz 0101','CHANGE 6000 1 1100 1100']
    output=None;trajectory=None;faults=0;states=set();idle=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if (root/(mode+'.stderr')).read_text():raise ValueError('Simulator diagnostic')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        normal=[line for line in lines if not line.startswith(('VI_','VIM_'))]
        if [line for line in normal if line.startswith('CHANGE ')]!=expected:raise ValueError('Changed electrical fixture transitions')
        if output is None:output=normal
        elif normal!=output:raise ValueError('Changed complete simulator output')
        controls=[line for line in lines if line.startswith(('VI_','VIM_'))];cursor=0;snapshots=[];layout=None
        def consume(line):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=line:raise ValueError('Missing/reordered observer record: '+line)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VI_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated snapshot')
            cursor+=1;return parse_snapshot(controls[start:cursor])
        for stage in range(7):
            consume(f'VIM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VIM_BEFORE');before=snapshot();validate_normal(before)
                current=fixture_state(before,stage)
                if layout is None:layout=current
                elif layout!=current:raise ValueError('Changed island/port lifetime or topology')
                consume('VIM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer mutated island state')
                if before['tick']!=(stage+1)*1000 or not before['islands']:raise ValueError('Wrong observation time/scope')
                for island in before['islands']:
                    idle+=int(not island['flag'])
                    states.update(b['state'] for b in island['branches'])
                snapshots.append(canonical(before))
                if mode=='corrupt':
                    for field in range(6):
                        consume(f'VIM_CHANGED {field}');changed=snapshot();changed_snapshot(before,changed,field)
                        consume('VIM_RESTORED')
                        if snapshot()!=before:raise ValueError('Fault not restored')
                        consume(f'VIM_FAULT {field} 1 1');faults+=1
            consume(f'VIM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Unexpected observer records')
        if snapshots:
            if trajectory is None:trajectory=snapshots
            elif trajectory!=snapshots:raise ValueError('Faults changed normal island trajectory')
    if states!={0,1,2} or not idle or faults!=42:raise ValueError('Missing state/fault coverage')
    return dict(completed=True,qualified=False,simulationOutputExactlyEqual=True,restoredFaults=faults,
                scope='Idle transmission-gate caches, strength vectors, branch enable state and mesh links; restored flag/input/output/strength/enable/link faults with unchanged full fixture output.',
                notEstablished=['Queued wrapper/island relationship','Board integration','Wire force/filter referents and thread state','Freed-storage equivalence and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/island_probe.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ISLAND_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('island_probe.py','fixtures/island_probe.c','fixtures/island_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Idle-island runtime controls verified; board and referent coverage remain open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
