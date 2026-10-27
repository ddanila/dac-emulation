#!/usr/bin/env python3
"""Qualify resolver tree and extension allocation after initial observation."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from resolver_probe import parse,changed,tree,PORTS,PULLS
from resolver_source_contract import layout
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def review(root):
    receipt=json.loads((root/'run.json').read_text());ordinary_reference=None;faults={};observations=callbacks=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native resolver control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=0;bindings={};leaves=[[b'']*n for n in PORTS];ordinary=[];drives=[];values=0;phase=0
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VRS_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Missing resolver footer')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if line.startswith('RES_DRIVE '):
                _,a,b,c=line.split();phase,core,port=map(int,(a,b,c));drives.append((phase,core,port))
                leaves[core][port]=bytes([0x66]*9 if phase==1 else [0xee]*9 if phase==2 else [0]*8+[0xee] if phase==3 else [0]*9)
                ordinary.append(line);cursor+=1;continue
            if line.startswith('RES_VALUE '):
                _,a,b,c=line.split();p,core=int(a),int(b)
                if p!=phase or bytes.fromhex(c)!=tree(leaves[core],PULLS[core])[-1]:raise ValueError('Output differs from independent driver resolution')
                ordinary.append(line);values+=1;cursor+=1;continue
            if '$finish called at 6000 (1ps)' in line:
                ordinary.append('finish');cursor+=1;continue
            a=line.split()
            if len(a)!=4 or a[:3]!=['RSM_API',str(stage),str(int(mode!='baseline'))] or a[3] not in ('0','1'):raise ValueError('Wrong resolver observation stage')
            callback=int(a[3]);cursor+=1
            if mode in ('enabled','corrupt'):
                consume('RSM_BEFORE');before=snapshot();consume('RSM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                if before['tick']!=(1000 if stage==1 else phase*1000):raise ValueError('Wrong native time')
                cores=[n for n in before['nodes'] if n['kind']==1];extensions=[n for n in before['nodes'] if n['kind']==2]
                if len(cores)!=(1 if stage==0 else 4) or len(extensions)!=(0 if stage==0 else 5):raise ValueError('Incomplete grown resolver population')
                sentinel=cores[0]
                if sentinel['ports']!=1 or sentinel['slots']!=1 or sentinel['pull'] or sentinel['vectors']!=[b''] or sentinel['output']!=sentinel['node'] or sentinel['values']!=sentinel['allocation']:raise ValueError('Changed persistent sentinel')
                if stage==1 and (phase or callback):raise ValueError('Missing new constructor observation')
                cores=cores[1:]
                for i,n in enumerate(cores):
                    expected=tree(leaves[i],PULLS[i])
                    if n['ports']!=PORTS[i] or n['slots']!=layout(PORTS[i])['slots'] or n['pull']!=PULLS[i] or n['vectors']!=expected:raise ValueError('Wrong leaf/branch/root cache')
                    if n['output']!=n['node'] or n['values']!=n['allocation']:raise ValueError('Wrong resolver allocation/output binding')
                expected_ext=[(cores[i]['fun'],base) for i,nports in enumerate(PORTS if stage else ()) for base in range(4,nports,4)]
                if [(n['core'],n['base']) for n in extensions]!=expected_ext:raise ValueError('Wrong extension routing')
                for n in before['nodes']:
                    identity=(n['node'],n['fun'],n['kind'],n.get('allocation'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Resolver allocation rebound')
                observations+=1;callbacks+=callback
                if mode=='corrupt' and not callback:
                    for n in before['nodes']:
                        for field in range(7 if n['kind']==1 else 2):
                            indices=range(n['slots']) if n['kind']==1 and field in (0,1,6) else [0]
                            for index in indices:
                                if n['kind']==1 and field in (0,6):
                                    v=n['vectors'][index]
                                    if not v or field==6 and not any(b in (0,136) for b in v):continue
                                consume(f"RSM_CHANGED {n['id']} {field} {index}");changed(before,snapshot(),n['id'],field,index)
                                consume('RSM_RESTORED')
                                if snapshot()!=before:raise ValueError('Resolver fault not restored')
                                consume(f"RSM_FAULT {n['id']} {field} {index} 1 1")
                                key=f"{n['kind']}:{field}";faults[key]=faults.get(key,0)+1
            consume(f'RSM_DONE {stage}');stage+=1
        if drives!=[(p,i,j) for p in range(1,6) for i,n in enumerate(PORTS) for j in range(n)] or not values or stage!=7+values:raise ValueError('Incomplete native continuation')
        if ordinary_reference is None:ordinary_reference=ordinary
        elif ordinary_reference!=ordinary:raise ValueError('Changed original-runtime continuation')
    if set(faults)!={f'1:{f}' for f in range(7)}|{'2:0','2:1'} or not callbacks:raise ValueError('Missing field/callback controls')
    return dict(qualified=False,controlsPassed=True,outputAndCachesMatchIndependentOracle=True,originalContinuationExactlyEqual=True,observations=observations,callbackObservations=callbacks,faultsByField=faults,scope='After a stable initial sentinel, admitted cores/extensions are allocated at 1 ns and observed before receiving inputs. Prior allocation identity persists. Native tri/tri0/tri1 resolver trees with 2/5/17 inputs, extended routing, strong conflicts, fresh-Z partial input replacement, repeated writes and synchronous downstream observation. Raw leaf/branch/root vectors, pull/port/output/allocation fields and extension links have restored faults. Allocation bounds remain stable under pointer/port-count corruption.',notEstablished=['Freed allocation/storage behavior','Single-input and other vector widths, additional raw input strengths and wired-logic support','Board binding, compact encoding and integration','General rollback and freed storage'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/resolver_growth.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_RESOLVER_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('resolver_growth.py','resolver_probe.py','resolver_source_contract.py','net_probe.py','fixtures/resolver_growth.cc','fixtures/resolver_growth.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native resolver cache-tree controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
