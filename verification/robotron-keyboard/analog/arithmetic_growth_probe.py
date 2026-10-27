#!/usr/bin/env python3
"""Reconstruct complete native arithmetic images from fixed-reference differences."""
import argparse,copy,re,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from arithmetic_probe import parse,changed,operands,oracle
from arithmetic_delta_probe import separate
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review_dense(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults={str(i):0 for i in range(4)}
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed arithmetic control')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('ARM_','VAR_'))]
        if ordinary[:-1]!=oracle() or not ordinary or '$finish called at 12000 (1ps)' not in ordinary[-1]:raise ValueError('Arithmetic output differs from independent oracle')
        lines=[l for l in lines if l.startswith(('ARM_','VAR_'))];cursor=0;stage=0;shots=[];bindings={};pointers={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VAR_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated arithmetic state')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            consume(f'ARM_API {stage} {int(mode!="baseline")} 0')
            if mode in ('enabled','corrupt'):
                consume('ARM_BEFORE');before=snapshot();consume('ARM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed arithmetic state')
                if before['tick']!=(0 if stage==0 else max(1,stage-1)*1000) or [n['kind'] for n in before['nodes']]!=([1] if stage==0 else [1,1,2,3,4,5]):raise ValueError('Wrong arithmetic growth observation')
                for n in before['nodes']:
                    identity=tuple(n[k] for k in ('node','fun','kind'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Arithmetic allocation rebound')
                    if n is before['nodes'][0]:
                        if n['width']!=3 or n['vectors']!=['222','222','333']:raise ValueError('Sentinel arithmetic changed')
                    elif n['width']!=80 or n['vectors']!=[*operands(max(0,stage-1)),'3'*80]:raise ValueError('Arithmetic operands differ from stimulus oracle')
                if mode=='corrupt':
                    for n in before['nodes']:
                        for field in range(4):
                            consume(f"ARM_CHANGED {n['id']} {field}");changed(before,snapshot(),n['id'],field)
                            consume('ARM_RESTORED')
                            if snapshot()!=before:raise ValueError('Arithmetic fault not restored')
                            consume(f"ARM_FAULT {n['id']} {field} 1 1");faults[str(field)]+=1
                image=copy.deepcopy(before)
                for n in image['nodes']:
                    for k in ('node','fun'):
                        if n[k] not in pointers:pointers[n[k]]=len(pointers)+1
                        n[k]=pointers[n[k]]
                shots.append(image)
            consume(f'ARM_DONE {stage}');stage+=1
        if stage!=13:raise ValueError('Missing arithmetic stages')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Arithmetic normal trajectory changed')
    if not all(faults.values()):raise ValueError('Missing arithmetic field controls')
    return dict(qualified=False,controlsPassed=True,normalTrajectoryExactlyEqual=True,outputMatchesIndependentOracle=True,
        restoredFaults=sum(faults.values()),faultsByField=faults,observationsPerRun=13,allocationGrowth=[1,6],
        scope='Five arithmetic objects allocated after a fixed one-object reference: 80-bit sum/subtraction/logical equality/case equality/case inequality operands, configured width and X fallback payload. Full and partial inputs, X/Z, unchanged-output cache writes and restored native faults preserve original-runtime output.',
        notEstablished=['Deletion and freed-storage equivalence','Other widths, empty operands and non-vector input paths','Board binding, budgets, integration and general rollback'])


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
    if not count or min(delta_bytes,reference_bytes,full_bytes)<=0:raise ValueError('Missing arithmetic delta evidence')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/arithmetic_growth_probe.cc' if ext=='cc' else 'fixtures/arithmetic_probe.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate/'vvp'),'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_ARITHMETIC_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('arithmetic_growth_probe.py','arithmetic_delta_probe.py','arithmetic_probe.py','net_probe.py','fixtures/arithmetic_growth_probe.cc','fixtures/arithmetic_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed arithmetic assessment')
        print('Exact arithmetic delta reconstruction and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
