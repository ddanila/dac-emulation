#!/usr/bin/env python3
"""Native sum/subtraction/equality payloads and exact restored-fault controls."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from arithmetic_probe import parse,changed
from arithmetic_delta_probe import separate
import tempfile
HERE=Path(__file__).resolve().parent


def operands(phase,width):
    a=b='2'*width
    for step in range(1,phase+1):
        port=int(step in (2,5,7,9,10))
        bits='1'*width if step==3 else '0'*width
        if step in (2,8):bits='1'+bits[1:]
        if step in (7,9):bits=bits[:-1]+'3'
        if step in (4,5):bits='2'*(width-1)+'3'
        if port:b=bits
        else:a=bits
    return a,b


def output(kind,a,b):
    width=len(a)
    if kind in (1,2):
        if set(a+b)-set('01'):return '3'*width
        x=int(a[::-1],2);y=int(b[::-1],2)
        return format((x+y if kind==1 else x-y) % (1<<width),f'0{width}b')[::-1]
    if kind==4:return str(int(a==b))
    if kind==5:return str(int(a!=b))
    if any(x in '01' and y in '01' and x!=y for x,y in zip(a,b)):return '0'
    return '3' if set(a+b)-set('01') else '1'


def oracle(width):
    return [f'ARITHMETIC_VALUE {phase*1000} {i} {output(i+1,*operands(phase,width))}'
            for phase in range(1,12) for i in range(5)]


def review_dense(root,width):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults={str(i):0 for i in range(4)}
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed arithmetic control')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('ARM_','VAR_'))]
        if ordinary[:-1]!=oracle(width) or not ordinary or '$finish called at 12000 (1ps)' not in ordinary[-1]:raise ValueError('Arithmetic output differs from independent oracle')
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
                if before['tick']!=stage*1000 or [n['kind'] for n in before['nodes']]!=list(range(1,6)):raise ValueError('Wrong arithmetic observation')
                for n in before['nodes']:
                    identity=tuple(n[k] for k in ('node','fun','kind'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Arithmetic allocation rebound')
                    if n['width']!=width or n['vectors']!=[*operands(stage,width),'3'*width]:raise ValueError('Arithmetic operands differ from stimulus oracle')
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
        if stage!=12:raise ValueError('Missing arithmetic stages')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Arithmetic normal trajectory changed')
    if not all(faults.values()):raise ValueError('Missing arithmetic field controls')
    return dict(qualified=False,controlsPassed=True,normalTrajectoryExactlyEqual=True,outputMatchesIndependentOracle=True,
        restoredFaults=sum(faults.values()),faultsByField=faults,observationsPerRun=12,
        scope='Allocated fixed-width sum/subtraction/logical equality/case equality/case inequality operands, configured width and X fallback payload. Full and partial inputs, X/Z, unchanged-output cache writes and restored native faults preserve original-runtime output.',
        notEstablished=['Untested widths, unequal/empty operands and non-vector input paths','Board binding, budgets, integration and general rollback'])


WIDTHS=(1,2,8,9,63,64,65)

def review(root):
    results={}
    for width in WIDTHS:
        source=root/str(width);count=full_bytes=delta_bytes=reference_bytes=0
        with tempfile.TemporaryDirectory() as folder:
            copied=Path(folder)
            for p in source.iterdir():
                if p.is_file():shutil.copy2(p,copied/p.name)
            for p in copied.glob('*.stdout'):
                lines,n,full,delta,reference=separate(p.read_text().splitlines())
                p.write_text('\n'.join(lines)+'\n' if lines else '')
                count+=n;full_bytes+=full;delta_bytes+=delta;reference_bytes+=reference
            result=review_dense(copied,width)
        if count!=528:raise ValueError('Missing width snapshot pairs')
        result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
        results[str(width)]=result
    return dict(qualified=False,controlsPassed=True,widths=list(WIDTHS),results=results,
        scope='Native arithmetic/comparison constructor, full/partial operand and restored-fault controls at board widths and either side of a 64-bit storage boundary. Original output and independent oracle agree, with exact dense/difference reconstruction.',
        notEstablished=['Unequal/empty operand widths, non-vector receives and arbitrary widths','Operational board integration and general rollback'])

def run_width(candidate,baseline,modules,out,width):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/arithmetic_width_probe.cc' if ext=='cc' else 'fixtures/arithmetic_probe.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11','-DARITHMETIC_WIDTH='+str(width),*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_ARITHMETIC_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('arithmetic_width_probe.py','arithmetic_probe.py','arithmetic_delta_probe.py','net_probe.py','fixtures/arithmetic_width_probe.cc','fixtures/arithmetic_probe.v')}),indent=2)+'\n')



def run(candidate,baseline,modules,out):
    out.mkdir(exist_ok=False)
    for width in WIDTHS:run_width(candidate,baseline,modules,out/str(width),width)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native arithmetic cache controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
