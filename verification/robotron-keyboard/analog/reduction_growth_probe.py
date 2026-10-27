#!/usr/bin/env python3
"""Reconstruct complete native reduction images from fixed-reference differences."""
import argparse,copy,re,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from reduction_probe import parse,changed,operand,oracle
from reduction_delta_probe import separate
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review_dense(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults={str(i):0 for i in range(2)}
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed reduction control')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('RDM_','VRD_'))]
        if ordinary[:-1]!=oracle() or not ordinary or '$finish called at 12000 (1ps)' not in ordinary[-1]:raise ValueError('Reduction output differs from independent oracle')
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
                if before['tick']!=(0 if stage==0 else max(1,stage-1)*1000) or [n['kind'] for n in before['nodes']]!=([5] if stage==0 else [5,1,2,3,4,5,6]):raise ValueError('Wrong reduction observation')
                for n in before['nodes']:
                    identity=tuple(n[k] for k in ('node','fun','kind'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Reduction allocation rebound')
                    if n['bits']!=('' if n is before['nodes'][0] else operand(max(0,stage-1))):raise ValueError('Reduction operand differs from stimulus oracle')
                if mode=='corrupt':
                    for n in before['nodes']:
                        for field in ([0,1] if n['bits'] else [1]):
                            consume(f"RDM_CHANGED {n['id']} {field}");changed(before,snapshot(),n['id'],field)
                            consume('RDM_RESTORED')
                            if snapshot()!=before:raise ValueError('Reduction fault not restored')
                            consume(f"RDM_FAULT {n['id']} {field} 1 1");faults[str(field)]+=1
                image=copy.deepcopy(before)
                for n in image['nodes']:
                    for k in ('node','fun'):
                        if n[k] not in pointers:pointers[n[k]]=len(pointers)+1
                        n[k]=pointers[n[k]]
                shots.append(image)
            consume(f'RDM_DONE {stage}');stage+=1
        if stage!=13:raise ValueError('Missing reduction stages')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Reduction normal trajectory changed')
    if not all(faults.values()):raise ValueError('Missing reduction field controls')
    return dict(qualified=False,controlsPassed=True,normalTrajectoryExactlyEqual=True,outputMatchesIndependentOracle=True,
        restoredFaults=sum(faults.values()),faultsByField=faults,observationsPerRun=13,allocationGrowth=[1,7],
        scope='Six objects allocated after a one-object reference: AND/OR/XOR/NAND/NOR/XNOR reduction operands. Empty constructor storage, partial-first initialization, full/partial updates, repeated input, resizing and empty-to-partial reuse are checked with restored native bit/vector faults and independent output agreement.',
        notEstablished=['Deletion and freed-storage equivalence','Board binding, budget and integration','General rollback and freed-storage equivalence'])

def review(root):
    count=full_bytes=delta_bytes=reference_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for p in copied.glob('*.stdout'):
            lines,n,full,delta,reference=separate(p.read_text().splitlines())
            p.write_text('\n'.join(lines)+'\n' if lines else '')
            count+=n;full_bytes+=full;delta_bytes+=delta;reference_bytes+=reference
        result=review_dense(copied)
    if not count or min(delta_bytes,reference_bytes,full_bytes)<=0:raise ValueError('Missing reduction delta evidence')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/reduction_growth_probe.cc' if ext=='cc' else 'fixtures/reduction_probe.v'),out/('probe.'+ext))
    # Extract declarations from the verified native source; reductions have no public header.
    source=(candidate/'vvp/reduce.cc').read_text();declarations=[]
    for name in ('base','and','or','xor','nand','nor','xnor'):
        marker='class vvp_reduce_'+name+' '
        start=source.index(marker);end=source.index('};',start)+2
        declarations.append(source[start:end])
    (out/'reduction_fixture.h').write_text('#include "vvp_net.h"\n'+'\n'.join(declarations)+'\n')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate/'vvp'),'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'reduction_fixture.h',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_REDUCTION_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('reduction_growth_probe.py','reduction_delta_probe.py','reduction_probe.py','net_probe.py','fixtures/reduction_growth_probe.cc','fixtures/reduction_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed reduction assessment')
        print('Exact reduction delta reconstruction and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
