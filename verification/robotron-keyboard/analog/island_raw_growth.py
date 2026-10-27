#!/usr/bin/env python3
"""Check raw island allocation growth against original native continuation."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from island_raw_probe import parse,bind,mutation
from island_probe import parse_snapshot
HERE=Path(__file__).resolve().parent

def review(root):
    receipt=json.loads((root/'run.json').read_text());reference=None;faults={};observations=0
    expected_ordinary=['GROW_PHASE 1','GROW_VALUE 1000 1 0','GROW_PHASE 2','GROW_VALUE 2000 1 1','GROW_VALUE 2000 2 111111111','GROW_PHASE 3','GROW_VALUE 3000 1 0','GROW_VALUE 3000 2 000000000','finish']
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native growth continuation')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=0;ordinary=[];identities={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot(raw=True):
            nonlocal cursor
            start=cursor;marker='VIR_END ' if raw else 'VI_END '
            while cursor<len(lines) and not lines[cursor].startswith(marker):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated growth state')
            cursor+=1;return parse(lines[start:cursor]) if raw else parse_snapshot(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if not line.startswith('IRM_STAGE '):
                ordinary.append('finish' if '$finish called at 4000 (1ps)' in line else line);cursor+=1;continue
            consume(f'IRM_STAGE {stage} 0 {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('IRM_BEFORE');before=snapshot();legacy=snapshot(False);bind(before,legacy)
                count=1 if stage==0 else 2 if stage<=2 else 3
                if before['tick']!=((stage+1)//2)*1000 or len(before['islands'])!=count:raise ValueError('Missing growth constructor or wrong time')
                for j,n in enumerate(before['islands']):
                    identity=(n['key'],tuple((p['id'],p['net'],p['functor'],p['filter']) for p in n['ports']))
                    if len(n['ports'])!=2 or identities.setdefault(n['id'],identity)!=identity:raise ValueError('Rebound existing island')
                    if n['id']!=j+1:raise ValueError('Missing allocation identity')
                    width=1 if j==1 else 9
                    empty=j==0 or j==1 and stage==1 or j==2 and stage==3
                    value=0x66 if stage in (2,3,6) else 0xee
                    for k,port in enumerate(n['ports']):
                        expected=dict(scratch=b'',**{'in':b'' if empty else bytes([value if k==0 else 0])*width,'out':b'' if empty else bytes([value])*width})
                        if port['vectors']!=expected:raise ValueError('Wrong independent constructor/input/output state')
                consume('IRM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                observations+=1
                if mode=='corrupt':
                    for field in range(3):
                        for op in range(3):
                            expected=mutation(before,field,op)
                            if expected is None:continue
                            consume(f'IRM_CHANGED {field} {op}');changed=snapshot();old=snapshot(False);bind(changed,old)
                            if changed!=expected:raise ValueError('Incorrect raw fault')
                            if op==1 and old!=legacy:raise ValueError('Raw collision changed legacy values')
                            consume('IRM_RESTORED')
                            if snapshot()!=before:raise ValueError('Growth fault not restored')
                            consume(f'IRM_FAULT {field} {op} 1 1');key=f'{field}:{op}';faults[key]=faults.get(key,0)+1
            consume(f'IRM_DONE {stage}');stage+=1
        if stage!=7 or ordinary!=expected_ordinary:raise ValueError('Incomplete or changed original continuation')
        if reference is None:reference=ordinary
        elif ordinary!=reference:raise ValueError('Changed native continuation')
    if set(faults)!={'0:0','0:1','0:2','1:0','1:2','2:2'}:raise ValueError('Missing growth fault controls')
    return dict(qualified=False,controlsPassed=True,observations=observations,faultsByField=faults,originalContinuationExactlyEqual=True,constructorAndCachesMatchIndependentExpectations=True,scope='An untouched initial island retains identity while native tran islands are allocated at later times, observed before input and driven at widths 1 and 9. Raw and legacy bindings agree; first-eligible byte, collision and width faults are restored before native continuation.',notEstablished=['Deleted allocations and freed storage','Live scratch in newly allocated islands and per-allocation fault targeting','Direct partial/raw-strength input coverage and other switch families','Compact encoding, operational board integration and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/island_raw_growth.'+ext),out/f'probe.{ext}')
    source=(candidate/'vvp/island_tran.cc').read_text()
    (out/'island_fixture.h').write_text('#include "vvp_island.h"\n'+source[source.index('class vvp_island_tran :'):source.index('vvp_island_branch_tran::vvp_island_branch_tran(')])
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'island_fixture.h',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ISLAND_RAW_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('island_raw_growth.py','island_raw_probe.py','island_probe.py','wire_raw_probe.py','net_probe.py','fixtures/island_raw_growth.cc','fixtures/island_raw_growth.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Raw island growth controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
