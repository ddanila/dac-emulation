#!/usr/bin/env python3
"""Observe retained native reduction operands through full and partial writes."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
HERE=Path(__file__).resolve().parent


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VRD_BEGIN','1']:raise ValueError('Invalid reduction header')
    tick=int(a[2]);nodes=[]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=7 or a[0]!='VRD_NODE':raise ValueError('Invalid reduction row')
        n=dict(id=int(a[1]),node=pointer(a[2]),fun=pointer(a[3]),kind=int(a[4]),bits='' if a[6]=='-' else a[6]);width=int(a[5])
        if n['kind'] not in range(1,7) or min(n[k] for k in ('id','node','fun'))<=0:raise ValueError('Invalid reduction identity')
        if width<0 or len(n['bits'])!=width or set(n['bits'])-set('0123'):raise ValueError('Invalid reduction operand')
        if nodes and n['id']<=nodes[-1]['id']:raise ValueError('Unordered reduction allocation')
        nodes.append(n)
    if tick<0 or not nodes or lines[-1]!=f'VRD_END {len(nodes)}':raise ValueError('Incomplete reduction image')
    for k in ('node','fun'):
        if len({n[k] for n in nodes})!=len(nodes):raise ValueError('Aliased reduction identities')
    return dict(tick=tick,nodes=nodes)


def changed(before,after,identity,field):
    expected=copy.deepcopy(before);n=next((n for n in expected['nodes'] if n['id']==identity),None)
    if n is None or field not in (0,1):raise ValueError('Invalid reduction fault')
    if field==1:n['bits']='3'*(len(n['bits'])+1)
    else:
        bits=n['bits']
        if not bits:raise ValueError('Empty bit fault target')
        n['bits']=('0' if bits[0]=='1' else '1')+bits[1:]
    if expected!=after:raise ValueError('Wrong reduction fault or unrelated change')


def operand(phase):
    return ['', '3'*70+'00'+'3'*8, '0'*80, '0'*71+'1'+'0'*8,
            '0'*71+'2'+'0'*8, '0'*71+'2'+'0'*8, '1'*80,
            '30'+'1'*78, '111', '110', '', '3'*79+'1'][phase]


def output(kind,bits):
    family=(kind-1)%3
    if family==0:value='0' if '0' in bits else '3' if set(bits)-set('01') else '1'
    elif family==1:value='1' if '1' in bits else '3' if set(bits)-set('01') else '0'
    else:value='3' if set(bits)-set('01') else str(bits.count('1')%2)
    return str(1-int(value)) if kind>3 and value in '01' else value


def oracle():
    return [f'REDUCTION_VALUE {phase*1000} {i} {output(i+1,operand(phase))}' for phase in range(1,12) for i in range(6)]


def review(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults={str(i):0 for i in range(2)}
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed reduction control')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('RDM_','VRD_'))]
        if ordinary[:-1]!=oracle() or not ordinary or '$finish called at 12000 (1ps)' not in ordinary[-1]:raise ValueError('Arithmetic output differs from independent oracle')
        lines=[l for l in lines if l.startswith(('RDM_','VRD_'))];cursor=0;stage=0;shots=[];bindings={};pointers={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VRD_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated reduction state')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            consume(f'RDM_API {stage} {int(mode!="baseline")} 0')
            if mode in ('enabled','corrupt'):
                consume('RDM_BEFORE');before=snapshot();consume('RDM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed reduction state')
                if before['tick']!=stage*1000 or [n['kind'] for n in before['nodes']]!=list(range(1,7)):raise ValueError('Wrong reduction observation')
                for n in before['nodes']:
                    identity=tuple(n[k] for k in ('node','fun','kind'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Arithmetic allocation rebound')
                    if n['bits']!=operand(stage):raise ValueError('Reduction operand differs from stimulus oracle')
                if mode=='corrupt':
                    for n in before['nodes']:
                        for field in ([0,1] if n['bits'] else [1]):
                            consume(f"RDM_CHANGED {n['id']} {field}");changed(before,snapshot(),n['id'],field)
                            consume('RDM_RESTORED')
                            if snapshot()!=before:raise ValueError('Arithmetic fault not restored')
                            consume(f"RDM_FAULT {n['id']} {field} 1 1");faults[str(field)]+=1
                image=copy.deepcopy(before)
                for n in image['nodes']:
                    for k in ('node','fun'):
                        if n[k] not in pointers:pointers[n[k]]=len(pointers)+1
                        n[k]=pointers[n[k]]
                shots.append(image)
            consume(f'RDM_DONE {stage}');stage+=1
        if stage!=12:raise ValueError('Missing reduction stages')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Arithmetic normal trajectory changed')
    if not all(faults.values()):raise ValueError('Missing reduction field controls')
    return dict(qualified=False,controlsPassed=True,normalTrajectoryExactlyEqual=True,outputMatchesIndependentOracle=True,
        restoredFaults=sum(faults.values()),faultsByField=faults,observationsPerRun=12,
        scope='Allocated AND/OR/XOR/NAND/NOR/XNOR reduction operands. Empty constructor storage, partial-first initialization, full/partial updates, repeated input, resizing and empty-to-partial reuse are checked with restored native bit/vector faults and independent output agreement.',
        notEstablished=['Unknown-subclass refusal controls and allocation lifecycle','Board binding, budget and integration','General rollback and freed-storage equivalence'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/reduction_probe.'+ext),out/('probe.'+ext))
    # Extract declarations from the verified native source; reductions have no public header.
    source=(candidate/'vvp/reduce.cc').read_text();declarations=[]
    for name in ('base','and','or','xor','nand','nor','xnor'):
        marker='class vvp_reduce_'+name+' '
        start=source.index(marker);end=source.index('};',start)+2
        declarations.append(source[start:end])
    (out/'reduction_fixture.h').write_text('#include "vvp_net.h"\n'+'\n'.join(declarations)+'\n')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'reduction_fixture.h',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_REDUCTION_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('reduction_probe.py','net_probe.py','fixtures/reduction_probe.cc','fixtures/reduction_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native reduction cache controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
