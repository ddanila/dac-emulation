#!/usr/bin/env python3
"""Review thread PCs against allocated native code slots without foreign dereferences."""
import argparse,json,os,platform,shutil,subprocess,tempfile,copy
from pathlib import Path
from ttl7406_probe import sha
from thread_compact_probe import parse_snapshot as parse_threads
from thread_probe import validate_normal
HERE=Path(__file__).resolve().parent

def pointer(s):return 0 if s=='(nil)' else int(s,16)


def parse_snapshot(lines):
    split=next((i for i,l in enumerate(lines) if l.startswith('VTC_BEGIN ')),None)
    if split is None:raise ValueError('Missing code binding')
    t=parse_threads(lines[:split]);a=lines[split].split();z=lines[-1].split()
    if len(a)!=3 or a[:2]!=['VTC_BEGIN','1'] or len(z)!=2 or z[0]!='VTC_END' or int(a[2])!=t['tick']:raise ValueError('Invalid code framing/time')
    code=[];seen=set()
    for line in lines[split+1:-1]:
        a=line.split()
        if len(a)!=5 or a[0]!='VTC_THREAD':raise ValueError('Invalid code binding record')
        identity=int(a[1]);pc=pointer(a[2]);index=int(a[3]);opcode=pointer(a[4])
        if identity<1 or identity in seen or min(pc,index,opcode)<0:raise ValueError('Invalid/duplicate code identity')
        seen.add(identity);code.append(dict(thread=identity,pc=pc,code=index,opcode=opcode))
    if len(code)!=int(z[1]):raise ValueError('Missing code binding')
    return dict(threads=t,code=code)


def validate(snapshot):
    validate_normal(snapshot['threads'])
    live={t['id']:t for t in snapshot['threads']['threads']}
    if {c['thread'] for c in snapshot['code']}!=set(live):raise ValueError('Incomplete thread/code binding')
    for c in snapshot['code']:
        if c['pc']!=live[c['thread']]['pc'] or not c['code'] or not c['opcode']:raise ValueError('Unallocated/invalid instruction binding')


def changed_snapshot(before,after,field):
    if field not in (3,11):raise ValueError('Unknown PC fault')
    expected=copy.deepcopy(before);t=expected['threads']['threads'][0];t['pc']=0 if field==3 else 1
    c=next(c for c in expected['code'] if c['thread']==t['id']);c.update(pc=t['pc'],code=0,opcode=0)
    if expected!=after:raise ValueError('Wrong PC binding fault or unrelated mutation')


def review(root):
    reference=None;trajectory=None;faults={3:0,11:0};addresses=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('VT_','VTC_','VTM_'))]
        controls=[l for l in lines if l.startswith(('VT_','VTC_','VTM_'))]
        if (root/(mode+'.stderr')).read_text():raise ValueError('Unexpected simulator diagnostic')
        if len(ordinary)!=2 or ordinary[0]!='VALUE 1000 512' or '$finish called at 2000 (1ps)' not in ordinary[1]:raise ValueError('Incomplete code-chunk continuation')
        if reference is None:reference=ordinary
        elif reference!=ordinary:raise ValueError('Changed complete output')
        cursor=0;shots=[];pointers={};codes={};pcs={}
        def consume(line):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=line:raise ValueError('Expected '+line)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VTC_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated code binding')
            cursor+=1;return parse_snapshot(controls[start:cursor])
        def canonical(p):
            if not p:return 0
            if p not in pointers:pointers[p]=len(pointers)+1
            return pointers[p]
        for stage,tick in enumerate((1000,1000,1000,2000)):
            consume(f'VTM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VTM_BEFORE');before=snapshot();validate(before)
                if before['threads']['tick']!=tick:raise ValueError('Wrong code observation time')
                consume('VTM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                consume('VTM_ADDRESS valid=1 foreign=1 null=1 misaligned=1');addresses+=1
                for c in before['code']:
                    binding=(c['pc'],c['opcode'])
                    if c['code'] in codes and codes[c['code']]!=binding:raise ValueError('Changed allocated code binding')
                    if c['pc'] in pcs and pcs[c['pc']]!=c['code']:raise ValueError('Aliased code identity')
                    codes[c['code']]=binding;pcs[c['pc']]=c['code']
                if mode=='corrupt':
                    for field in (3,11):
                        consume(f'VTM_CHANGED {field}');changed_snapshot(before,snapshot(),field)
                        consume('VTM_RESTORED')
                        if snapshot()!=before:raise ValueError('PC fault not restored')
                        consume(f'VTM_FAULT {field} 1 1');faults[field]+=1
                normalized=copy.deepcopy(before)
                for t in normalized['threads']['threads']:
                    for key in ('pc','scope','writeContext','readContext','event'):t[key]=canonical(t[key])
                    t['objects']=[canonical(p) for p in t['objects']]
                for c in normalized['code']:
                    for key in ('pc','opcode'):c[key]=canonical(c[key])
                shots.append(normalized)
            consume(f'VTM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Extra code control records')
        if shots:
            if max(codes)-min(codes)<1024:raise ValueError('Missing multiple-code-chunk coverage')
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Faults changed normal internal trajectory')
    if not all(faults.values()) or addresses!=8:raise ValueError('Missing code fault/address controls')
    return dict(completed=True,qualified=False,simulationOutputExactlyEqual=True,normalStateTrajectoryExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,addressProbeBoundaries=addresses,scope='Thread PCs bound to allocated code-slot and opcode identities across code chunks; null/foreign/misaligned addresses rejected without dereference and PC faults restored before continuation.',notEstablished=['Board integration','Complete code operands and mutable referenced objects','Static-code immutability proof or arbitrary code writes','Freed-code storage and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/code_binding_probe.c' if ext=='c' else 'fixtures/code_binding_probe.v'),out/f'probe.{ext}')
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
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('code_binding_probe.py','thread_probe.py','thread_compact_probe.py','fixtures/code_binding_probe.c','fixtures/code_binding_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Thread PC allocation bindings and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
