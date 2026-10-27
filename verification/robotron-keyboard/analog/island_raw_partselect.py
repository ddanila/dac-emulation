#!/usr/bin/env python3
"""Check native island part-select routing and unequal endpoint widths."""
import argparse,copy,json,lzma,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from island_raw_probe import parse,bind
from island_probe import parse_snapshot,validate_normal
from resolver_strength_oracle import scalar
from strength_switch_probe import seed
from wire_raw_probe import triplet
HERE=Path(__file__).resolve().parent

def targeted(before,island,port,field,op):
    result=copy.deepcopy(before);v=result['islands'][island]['ports'][port]['vectors'];name=('in','out','scratch')[field];value=bytearray(v[name])
    if op!=2 and (not value or op==1 and not any(x in (0,136) for x in value)):return None
    if op==2:value=bytearray(len(value)+1)
    else:
        i=next(i for i,x in enumerate(value) if x in (0,136)) if op==1 else 0
        value[i]=value[i]^136 if op==1 else 102 if value[i]==238 else 238
    v[name]=bytes(value);return result


SPECS=((9,1,8),(9,8,1),(80,9,63),(80,8,0))

INPUTS=((0x66,0xee),(0x33,0xee),(0xee,0x55),(0x81,0xd3),(0x88,0x00),(0x00,0x88),(0xff,0x66),(0x77,0xee),(0xb5,0xd3),(0xee,0xee),(0xee,0xee),(0,0))

def resolved(inputs,spec):
    width,part,offset=spec;a=bytes([inputs[0]])*width;b=bytes([inputs[1]])*part
    for _ in range(32):
        next_b=bytes(scalar(b[k],a[offset+k]) for k in range(part))
        next_a=bytes(scalar(a[k],next_b[k-offset] if offset<=k<offset+part else 0) for k in range(width))
        if (next_a,next_b)==(a,b):return a,b
        a,b=next_a,next_b
    raise ValueError('Part-select propagation did not settle')

def output_text(root,mode):
    p=root/(mode+'.stdout')
    return p.read_text() if p.exists() else lzma.open(str(p)+'.xz','rt').read()

def review(root):
    receipt=json.loads((root/'run.json').read_text());reference=None;faults={};observations=0
    want_ordinary=[]
    for phase in range(1,len(INPUTS)+1):
        want_ordinary.append(f'GROW_PHASE {phase}')
        for index,spec in enumerate(SPECS):
            value=resolved(INPUTS[phase-1],spec)[1]
            if phase==1 or value!=resolved(INPUTS[phase-2],spec)[1]:want_ordinary.append(f'GROW_VALUE {phase*1000} {index} '+value.hex())
    want_ordinary.append('finish')
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native callback continuation')
        lines=output_text(root,mode).splitlines();cursor=stage=phase=0;ordinary=[];identities={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot(raw=True):
            nonlocal cursor
            start=cursor;marker='VIR_END ' if raw else 'VI_END '
            while cursor<len(lines) and not lines[cursor].startswith(marker):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated callback state')
            cursor+=1;return parse(lines[start:cursor]) if raw else parse_snapshot(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if not line.startswith('IRM_STAGE '):
                if line.startswith('GROW_PHASE '):phase=int(line.split()[1])
                ordinary.append('finish' if '$finish called at 13000 (1ps)' in line else line);cursor+=1;continue
            expected_callbacks=(0,)*(len(INPUTS)+1)
            if stage>=len(expected_callbacks):raise ValueError('Extra observation')
            callback=expected_callbacks[stage];consume(f'IRM_STAGE {stage} {callback} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('IRM_BEFORE');before=snapshot();legacy=snapshot(False);bind(before,legacy);validate_normal(legacy)
                if before['tick']!=phase*1000 or len(before['islands'])!=4 or phase!=stage:raise ValueError('Wrong population or time')
                for j,n in enumerate(before['islands']):
                    mesh=legacy['islands'][j]
                    if mesh['flag'] or len(mesh['branches'])!=1:raise ValueError('Unexpected pending or additional branch')
                    branch=mesh['branches'][0];width,part,offset=SPECS[j]
                    if tuple(branch[k] for k in ('width','part','offset','active','resistive','state','enable','a','b'))!=(width,part,offset,1,0,1,0,1,2):raise ValueError('Wrong part-select routing')
                    identity=(n['key'],tuple((p['id'],p['net'],p['functor'],p['filter']) for p in n['ports']))
                    if n['id']!=j+1 or len(n['ports'])!=2 or identities.setdefault(n['id'],identity)!=identity:raise ValueError('Rebound allocation identity')
                    for k,port in enumerate(n['ports']):
                        inp=bytes([INPUTS[phase-1][k]])*SPECS[j][k] if phase else b'';out=resolved(INPUTS[phase-1],SPECS[j])[k] if phase else b'';scratch=b''
                        expected={'in':inp,'out':out,'scratch':scratch}
                        if port['vectors']!=expected:raise ValueError('Wrong independent callback cache state')
                consume('IRM_REPEAT')
                if snapshot()!=before:raise ValueError('Observation changed state')
                observations+=1
                if mode=='corrupt':
                    for j in range(4):
                        for k in range(2):
                            for field in range(3):
                                for op in range(3):
                                    expected=targeted(before,j,k,field,op)
                                    if expected is None:continue
                                    consume(f'IRM_CHANGED {j+1} {k+1} {field} {op}');changed=snapshot();old=snapshot(False);bind(changed,old)
                                    if [(n['branches'],n['flag'],n['head']) for n in old['islands']]!=[(n['branches'],n['flag'],n['head']) for n in legacy['islands']]:raise ValueError('Raw fault changed mesh topology or branch state')
                                    if changed!=expected:raise ValueError('Wrong targeted fault or unrelated change')
                                    if op==1 and old!=legacy:raise ValueError('Collision visible in legacy view')
                                    consume('IRM_RESTORED')
                                    if snapshot()!=before:raise ValueError('Targeted fault not restored')
                                    key=f'{j}:{k}:{field}:{op}';faults[key]=faults.get(key,0)+1
            consume(f'IRM_DONE {stage}');stage+=1
        if stage!=len(INPUTS)+1 or ordinary!=want_ordinary:raise ValueError('Changed original native continuation')
        if reference is None:reference=ordinary
        elif ordinary!=reference:raise ValueError('Observer changed continuation')
    required={f'{j}:{k}:{field}:2' for j in range(4) for k in range(2) for field in range(3)}|{f'{j}:0:0:0' for j in range(4)}
    if not required.issubset(faults):raise ValueError('Missing input fault controls')
    return dict(qualified=False,controlsPassed=True,observations=observations,faultsByTarget=faults,originalContinuationExactlyEqual=True,scope='Native part-select branches join unequal-width endpoints at low/high offsets and across a storage-word boundary. Competing strong, weak, asymmetric, supply and raw HiZ inputs match independent slice/expansion expectations and original outputs. Complete raw caches, branch parameters, endpoint identities and targeted restored faults are checked.',notEstablished=['Feedback-driven enables, other input sequences and more complex meshes','Deleted allocations and freed storage','Compact encoding, operational board integration and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/island_raw_partselect.'+ext),out/f'probe.{ext}')
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
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('island_raw_partselect.py','resolver_strength_oracle.py','strength_switch_probe.py','island_raw_probe.py','island_probe.py','wire_raw_probe.py','net_probe.py','fixtures/island_raw_partselect.cc','fixtures/island_raw_partselect.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Raw island strength-input controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
