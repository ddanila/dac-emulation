#!/usr/bin/env python3
"""Matched synchronization callback header, cancellation and executing-state controls."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def snapshot(lines):
    a=lines[0].split()
    if len(a)!=5 or a[:2]!=['VS_BEGIN','1'] or lines[-1]!='VS_END':
        raise ValueError('Invalid snapshot framing')
    now,mode,count=map(int,a[2:]);items=[]
    if now<0 or mode<0 or count<0:raise ValueError('Invalid header')
    for line in lines[1:-1]:
        fields=line.split()
        if len(fields)!=18 or fields[0]!='VS_CALLBACK':raise ValueError('Invalid callback record')
        values=list(map(int,fields[1:-1]));real=float.fromhex(fields[-1])
        ident,executing,sync,reason,index,active,function,user,obj,value,nxt,back,timeptr,typ,high,low=values
        if ident<1 or (items and ident<=items[-1][0]):raise ValueError('Invalid lifetime ordering')
        if any(v not in (0,1) for v in (executing,active,function,user,obj,value,nxt,back,timeptr)):
            raise ValueError('Invalid boolean')
        # This fixture supplies null referents and the same function/user identity.
        if sync not in (0,1) or function!=active or not all((user,obj,value,nxt,back,timeptr)):
            raise ValueError('Uncovered callback identity or referent')
        if typ!=2 or high!=0 or low<0 or real!=0 or reason!=9 or index not in (1,2,3):
            raise ValueError('Unexpected fixture callback data')
        items.append(values)
    if len(items)!=count or sum(x[1] for x in items)>1:raise ValueError('Incomplete live registry')
    return {'time':now,'mode':mode,'callbacks':items}


def review(root):
    observations={};baseline=None;faults=0;executing=0;canceled=0
    for name in ('baseline','disabled','enabled','corrupt'):
        text=(root/(name+'.stdout')).read_text()
        if (root/(name+'.stderr')).read_text():raise ValueError('Runtime diagnostic')
        output=[x for x in text.splitlines() if not x.startswith('VS_')]
        if baseline is None:baseline=output
        if output!=baseline:raise ValueError('Changed HDL/callback execution')
        expected=[f'CALLBACK 0 {base+delay} {index}' for base in (2000,12000,22000) for delay,index in ((1000,1),(3000,3))]
        if [x for x in output if x.startswith('CALLBACK ')]!=expected:raise ValueError('Missing callback or cancellation failed')
        blocks=[];current=[];groups=[]
        for line in text.splitlines():
            if line.startswith('VS_API '):
                if line!=f'VS_API {int(name!="baseline")}':raise ValueError('Wrong loaded runtime')
                groups.append({'shots':[],'fault':None})
            elif line.startswith('VS_BEGIN '):
                if current:raise ValueError('Nested snapshot')
                current=[line]
            elif line=='VS_END':
                if not current:raise ValueError('Orphan end')
                current.append(line);snapshot(current);groups[-1]['shots'].append(current);current=[]
            elif line.startswith('VS_CALLBACK '):
                if not current:raise ValueError('Orphan callback')
                current.append(line)
            elif line.startswith('VS_FAULT '):
                if groups[-1]['fault'] is not None:raise ValueError('Duplicate fault result')
                groups[-1]['fault']=int(line.split()[1])
            elif line.startswith('VS_'):raise ValueError('Unknown observer record')
        if current or len(groups)!=9:raise ValueError('Missing observations')
        for i,g in enumerate(groups):
            shots=g['shots'];fault=g['fault'];enabled=name in ('enabled','corrupt')
            expected_fault=int(i%3!=2) if name=='corrupt' else None
            if fault!=expected_fault or len(shots)!=(2+2*(fault==1) if enabled else 0):
                raise ValueError('Missing snapshot or fault coverage')
            if not enabled:continue
            if shots[0]!=shots[1]:raise ValueError('Observation changed callback state')
            state=snapshot(shots[0]);items=state['callbacks']
            if state['mode']!=(3 if i%3==0 else 4):raise ValueError('Wrong executing VPI mode')
            expected_ids=list(range(1+3*(i//3),4+3*(i//3))) if i%3!=2 else [3+3*(i//3)]
            if [x[0] for x in items]!=expected_ids:raise ValueError('Wrong callback lifetime')
            if state['time']!=(2000,12000,22000)[i//3]+(0,1000,3000)[i%3]:raise ValueError('Wrong sample time')
            if len(items)!=(3,3,1)[i%3] or sum(x[1] for x in items)!=int(i%3!=0):raise ValueError('Missing executing/live callback')
            if sum(not x[5] for x in items)!=int(i%3!=2):raise ValueError('Missing canceled callback')
            for item in items:
                index=item[4]
                expected_executing=int(i%3!=0 and index==(1 if i%3==1 else 3))
                expected_low=state['time'] if expected_executing else index*1000
                if item[1]!=expected_executing or item[2]!=0 or item[5]!=int(index!=2) or item[15]!=expected_low:
                    raise ValueError('Wrong callback payload or executing identity')
            executing+=sum(x[1] for x in items);canceled+=sum(not x[5] for x in items)
            if fault:
                altered=snapshot(shots[2]);restored=snapshot(shots[3])
                if restored!=state or altered==state or altered['time']!=state['time'] or altered['mode']!=state['mode'] or len(altered['callbacks'])!=len(items):raise ValueError('Undetected or unrestored mode mutation')
                changed=[j for j,(a,b) in enumerate(zip(items,altered['callbacks'])) if a!=b]
                if len(changed)!=1:raise ValueError('Mutation affected multiple callbacks')
                j=changed[0];a=items[j];b=altered['callbacks'][j]
                if a[1] or not a[5] or a[:2]+a[3:]!=b[:2]+b[3:] or a[2]==b[2]:raise ValueError('Wrong mutation target')
                faults+=1
            blocks.append(state)
        observations[name]=blocks
    if faults!=6 or executing!=12 or canceled!=12:raise ValueError('Coverage incomplete')
    return {'completed':True,'qualified':False,'timestampedOutputExactlyEqual':True,
            'modeMutationsDetectedAndRestored':faults,'executingObservations':executing,
            'canceledObservations':canceled,'inventories':observations,
            'scope':'Live synchronization callback headers and executing callback identity in a standalone fixture.',
            'notEstablished':['Board bridge integration','User-data/object/value referent contents','Executing C++ stack and generic scheduler wrapper','Other event payloads','Freed storage and general rollback']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed candidate build')
    shutil.copyfile(HERE/'fixtures/private_sync_probe.c',out/'probe.c')
    shutil.copyfile(HERE/'fixtures/private_sync_probe.v',out/'probe.v')
    subprocess.run(['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    subprocess.run(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')],check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',*modules.glob('*.vpi')]
    runtime={str(p):sha(p) for p in paths};commands={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_SYNC_PROBE=mode)
        env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];commands[name]=cmd
        p=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr);p.check_returncode()
    if any(sha(Path(p))!=h for p,h in runtime.items()):raise ValueError('Changed runtime')
    result=review(out);result.update(runtime=runtime,commands=commands,candidateBuildSha256=sha(candidate/'build.json'),
        sources={n:sha(HERE/n) for n in ('private_sync_probe.py','fixtures/private_sync_probe.c','fixtures/private_sync_probe.v','build_private_sync_observer.py','engine-patches/icarus-sync-observer.patch','engine-patches/icarus-queue-observer.patch')})
    shutil.copyfile(candidate/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(out/'assessment.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        measured=review(a.check);retained=json.loads((a.check/'assessment.json').read_text())
        if any(retained.get(k)!=v for k,v in measured.items()):raise ValueError('Changed assessment')
        print('Synchronization callback fixture controls verified; board qualification remains open.')
    else:
        if any(x is None for x in (a.candidate,a.baseline,a.modules,a.out)):p.error('Need candidate, baseline, modules and out')
        run(a.candidate,a.baseline,a.modules,a.out)
