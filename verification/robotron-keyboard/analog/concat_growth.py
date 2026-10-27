#!/usr/bin/env python3
"""Qualify native concatenation allocations created after initial observation."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from concat_probe import parse,changed,expected
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def review(root):
    receipt=json.loads((root/'run.json').read_text());faults={str(i):0 for i in range(7)};executing=0;observations=0
    wanted=[]
    for phase in range(1,9):
        for i,kind in enumerate((4,8)):
            if kind==4 and phase in (4,6,7,8):continue
            wanted.append(f'CONCAT_VALUE {phase*1000} {i} {expected(phase,kind)}')
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native concat control failed')
        all_lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in all_lines if l.startswith('CONCAT_VALUE ') or '$finish' in l]
        if ordinary[:-1]!=wanted or not ordinary or '$finish called at 9000 (1ps)' not in ordinary[-1]:raise ValueError('Native output differs from independent concat oracle')
        lines=[l for l in all_lines if l not in ordinary];cursor=0;stage=0;bindings={};phases=set()
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VCN_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Incomplete concat snapshot')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            a=lines[cursor].split()
            if len(a)!=4 or a[:3]!=['CNM_API',str(stage),str(int(mode!='baseline'))] or a[3] not in ('0','1'):raise ValueError('Wrong concat stage')
            callback=int(a[3]);cursor+=1
            if mode in ('enabled','corrupt'):
                consume('CNM_BEFORE');before=snapshot();consume('CNM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed native state')
                phase=before['tick']//1000
                if before['tick']!=phase*1000 or phase not in range(9) or [n['kind'] for n in before['nodes']]!=([8] if stage==0 else [8,4,8]):raise ValueError('Wrong observation population/time')
                if stage==0 and (phase or callback):raise ValueError('Missing pre-growth inventory')
                if stage==1 and (phase!=1 or callback):raise ValueError('Missing post-allocation constructor inventory')
                if not callback:phases.add(phase)
                for index,n in enumerate(before['nodes']):
                    identity=tuple(n[k] for k in ('node','fun','kind','event'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Rebound concat allocation')
                    if index==0:
                        if n['widths']!=[1,0,0,0] or n['width']!=1 or n['bits']!='00' or n['pending']:raise ValueError('Changed persistent sentinel')
                    elif n['widths']!=[1,8,9,80] or n['width']!=98 or n['bits']!=expected(0 if stage==1 else phase,n['kind']):raise ValueError('Wrong new native cache state')
                    es=[e for e in before['events'] if e['key']==n['event']]
                    if n['pending']:
                        if n['pending']!=n['node'] or len(es)!=1 or es[0]['region']=='executing':raise ValueError('Missing queued binding')
                    elif es and (len(es)!=1 or es[0]['region']!='executing' or es[0]['slot']!=-2):raise ValueError('Wrong executing binding')
                keys={n['event'] for n in before['nodes']}
                if any(e['key'] not in keys or e['delete']!=0 or e['id']<=0 for e in before['events']):raise ValueError('Foreign event binding')
                active=sum(e['region']=='executing' for e in before['events'])
                if active!=callback:raise ValueError('Missing executing observation')
                executing+=active;observations+=1
                if mode=='corrupt' and not callback:
                    for n in before['nodes']:
                        fields=list(range(5))+([5] if n['pending'] else [])+([6] if n['kind']==8 and any(b in (0,136) for b in bytes.fromhex(n['bits'])) else [])
                        for field in fields:
                            consume(f"CNM_CHANGED {n['id']} {field}");changed(before,snapshot(),n['id'],field)
                            consume('CNM_RESTORED')
                            if snapshot()!=before:raise ValueError('Native fault not restored')
                            consume(f"CNM_FAULT {n['id']} {field} 1 1");faults[str(field)]+=1
            consume(f'CNM_DONE {stage}');stage+=1
        if stage!=22 or (mode in ('enabled','corrupt') and phases!=set(range(9))):raise ValueError('Incomplete native trajectory')
    if not all(faults.values()) or not executing:raise ValueError('Missing native field coverage')
    return dict(qualified=False,controlsPassed=True,outputMatchesIndependentOracle=True,observations=observations,executingObservations=executing,faultsByField=faults,scope='Supported concat allocations grow from a persistent sentinel to additional concat4/concat8 objects at 1 ns. New constructor state precedes writes; original-runtime continuation, unchanged sentinel and stable identities persist. Concat4/concat8 constructor, four input ports, partial writes, unchanged-write scheduling, raw strength collisions and queued/executing wrapper bindings. Native faults restore caches, each port width and pending output nodes before continuation.',notEstablished=['Freed allocation/storage behavior','Compact reconstruction of new rows and operational board integration','General rollback and freed storage'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/concat_growth.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_CONCAT_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('concat_growth.py','concat_probe.py','net_probe.py','fixtures/concat_growth.cc','fixtures/concat_growth.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native concatenation cache controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
