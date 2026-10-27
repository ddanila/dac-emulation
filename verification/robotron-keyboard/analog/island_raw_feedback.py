#!/usr/bin/env python3
"""Check native feedback-driven enables and intermediate island outputs."""
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


WIDTHS=(1,9)*4

INPUTS=((0x66,0),(0xee,0),(0,0xee),(0,0x66),(0xee,0x66),(0x66,0xee),(0x88,0),(0,0x88),(0xe6,0xee),(0x66,0x66))

def transmitted(raw,resistive,unknown=False):
    bit,s0,s1=map(int,triplet(raw));mapping=(0,1,1,2,2,3,5,5) if resistive else (0,1,2,3,4,5,6,6)
    result=seed(bit,mapping[s0],mapping[s1])
    bit,s0,s1=map(int,triplet(result))
    if unknown and bit==0:return seed(3,s0,0)
    if unknown and bit==1:return seed(3,0,s1)
    return result

def resolved(inputs,resistive,state):
    a,b=inputs
    if state==0:return a,b
    for _ in range(32):
        next_b=scalar(b,transmitted(a,resistive,state==2));next_a=scalar(a,transmitted(next_b,resistive,state==2))
        if (next_a,next_b)==(a,b):return a,b
        a,b=next_a,next_b
    raise ValueError('Strength propagation did not settle')

def control_state(raw,active):
    bit=int(triplet(raw)[0]);return 2 if bit>1 else int(bit==active)

def settle_feedback(inputs,resistive,active,previous):
    state=control_state(previous[0] if previous is not None else inputs[0],active)
    outputs=previous;emitted=[];states=[]
    for _ in range(16):
        if state in states:raise ValueError('Unsettled feedback cycle')
        states.append(state);new=resolved(inputs,resistive,state)
        if outputs is None or outputs[1]!=new[1]:emitted.append(new[1])
        outputs=new;next_state=control_state(outputs[0],active)
        if next_state==state:return outputs,state,emitted,states
        state=next_state
    raise ValueError('Feedback did not settle')

def expectations():
    outputs=[None]*8;history={};ordinary=[];reruns=0
    for phase,inputs in enumerate(INPUTS,1):
        ordinary.append(f'GROW_PHASE {phase}')
        for j,width in enumerate(WIDTHS):
            value,state,emitted,states=settle_feedback(inputs,j>=4,int(j%4>=2),outputs[j]);outputs[j]=value;history[phase,j]=(value,state)
            reruns+=len(states)-1
            ordinary.extend(f'GROW_VALUE {phase*1000} {j} '+(bytes([raw])*width).hex() for raw in emitted)
    ordinary.append('finish');return history,ordinary,reruns

def expected_input(phase,width,port):
    return bytes([INPUTS[phase-1][port]])*width if phase else b''

def output_text(root,mode):
    p=root/(mode+'.stdout')
    return p.read_text() if p.exists() else lzma.open(str(p)+'.xz','rt').read()

def review(root):
    receipt=json.loads((root/'run.json').read_text());reference=None;faults={};observations=0
    history,want_ordinary,reruns=expectations()
    if not reruns:raise ValueError('Missing feedback reevaluation')
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
                ordinary.append('finish' if '$finish called at 11000 (1ps)' in line else line);cursor+=1;continue
            expected_callbacks=(0,)*(len(INPUTS)+1)
            if stage>=len(expected_callbacks):raise ValueError('Extra observation')
            callback=expected_callbacks[stage];consume(f'IRM_STAGE {stage} {callback} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('IRM_BEFORE');before=snapshot();legacy=snapshot(False);bind(before,legacy);validate_normal(legacy)
                if before['tick']!=phase*1000 or len(before['islands'])!=8 or phase!=stage:raise ValueError('Wrong population or time')
                for j,n in enumerate(before['islands']):
                    mesh=legacy['islands'][j]
                    if mesh['flag'] or len(mesh['branches'])!=1:raise ValueError('Unexpected pending island or branch population')
                    branch=mesh['branches'][0]
                    expected_branch=(0,0,0,int(j%4>=2),int(j>=4),history[phase,j][1] if phase else 0,n['ports'][0]['net'],1,2)
                    if tuple(branch[k] for k in ('width','part','offset','active','resistive','state','enable','a','b'))!=expected_branch:raise ValueError('Wrong enable binding or conditional branch state')
                    identity=(n['key'],tuple((p['id'],p['net'],p['functor'],p['filter']) for p in n['ports']))
                    if n['id']!=j+1 or len(n['ports'])!=2 or identities.setdefault(n['id'],identity)!=identity:raise ValueError('Rebound allocation identity')
                    for k,port in enumerate(n['ports']):
                        inp=expected_input(phase,WIDTHS[j],k);out=bytes([history[phase,j][0][k]])*WIDTHS[j] if phase and k<2 else b'';scratch=b''
                        expected={'in':inp,'out':out,'scratch':scratch}
                        if port['vectors']!=expected:raise ValueError('Wrong independent callback cache state')
                consume('IRM_REPEAT')
                if snapshot()!=before:raise ValueError('Observation changed state')
                observations+=1
                if mode=='corrupt':
                    for j in range(8):
                        for k in range(2):
                            for field in range(3):
                                for op in range(3):
                                    expected=targeted(before,j,k,field,op)
                                    if expected is None:continue
                                    consume(f'IRM_CHANGED {j+1} {k+1} {field} {op}');changed=snapshot();old=snapshot(False);bind(changed,old)
                                    if [(n['branches'],n['flag'],n['head']) for n in old['islands']]!=[(n['branches'],n['flag'],n['head']) for n in legacy['islands']]:raise ValueError('Raw fault changed mesh topology or control state')
                                    if changed!=expected:raise ValueError('Wrong targeted fault or unrelated change')
                                    if op==1 and old!=legacy:raise ValueError('Collision visible in legacy view')
                                    consume('IRM_RESTORED')
                                    if snapshot()!=before:raise ValueError('Targeted fault not restored')
                                    key=f'{j}:{k}:{field}:{op}';faults[key]=faults.get(key,0)+1
            consume(f'IRM_DONE {stage}');stage+=1
        if stage!=len(INPUTS)+1 or ordinary!=want_ordinary:raise ValueError('Changed original native continuation')
        if reference is None:reference=ordinary
        elif ordinary!=reference:raise ValueError('Observer changed continuation')
    required={f'{j}:{k}:{field}:2' for j in range(8) for k in range(2) for field in range(3)}|{f'{j}:0:0:0' for j in range(8)}
    if not required.issubset(faults):raise ValueError('Missing input fault controls')
    return dict(qualified=False,controlsPassed=True,observations=observations,faultsByTarget=faults,originalContinuationExactlyEqual=True,feedbackReevaluations=reruns,scope='Native tranif0/tranif1 and resistive variants use resolved endpoint A as enable. A history-aware endpoint model predicts branch reevaluations, intermediate output emissions and final raw caches for both control polarities. Targeted faults restore before continuation; original-runtime output and enable/topology bindings remain exact.',notEstablished=['Oscillating feedback networks, arbitrary input sequences and more complex meshes','Deleted allocations and freed storage','Compact encoding, operational board integration and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/island_raw_feedback.'+ext),out/f'probe.{ext}')
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
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('island_raw_feedback.py','resolver_strength_oracle.py','strength_switch_probe.py','island_raw_probe.py','island_probe.py','wire_raw_probe.py','net_probe.py','fixtures/island_raw_feedback.cc','fixtures/island_raw_feedback.v')}},indent=2)+'\n')
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
