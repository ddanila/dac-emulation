#!/usr/bin/env python3
"""Native assignment subclass refusals and nested execution ownership."""
import argparse,json,lzma,os,platform,shutil,subprocess
from pathlib import Path
from assignment_raw import parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
CASES=[('family',timing,family) for timing in ('early','late') for family in (1,2,3)]+[('nested','early',family) for family in (0,1,2)]

def output(root,name):
    p=root/(name+'.stdout')
    return p.read_text() if p.exists() else lzma.open(str(p)+'.xz','rt').read()

def review(root):
    receipt=json.loads((root/'run.json').read_text());refusals=admissions=nested_frames=0
    for kind,timing,family in CASES:
        reference=None;case=f'{kind}-{timing}-{family}'
        for mode in ('original','disabled','observe'):
            name=case+'-'+mode
            if receipt['runs'][name]['exitCode'] or (root/(name+'.stderr')).read_text():raise ValueError('Native execution failed')
            lines=output(root,name).splitlines();cursor=0;ordinary=[];stage=0;observed=[];targets={};outer={};lifetime_max=0
            while cursor<len(lines):
                line=lines[cursor];cursor+=1
                if not line.startswith('AF_OBSERVE '):
                    ordinary.append('finish' if '$finish called at 2000 (1ps)' in line else line);continue
                a=line.split()
                if len(a)!=5 or int(a[1])!=stage or mode!='observe':raise ValueError('Unexpected observation')
                phase=int(a[2]);label=a[3];result=int(a[4]);stage+=1
                expected_refusal=(kind=='family' and (phase==1 or timing=='early') and label!='settled') or (kind=='nested' and family!=0 and label=='inner')
                if result!=(-1 if expected_refusal else 0):raise ValueError('Wrong native admission/refusal')
                observed.append((phase,label))
                if expected_refusal:
                    if cursor>=len(lines) or lines[cursor]!='AF_REFUSED_EMPTY':raise ValueError('Partial or missing refusal')
                    cursor+=1;refusals+=1;continue
                start=cursor
                while cursor<len(lines) and not lines[cursor].startswith('VAR_END '):cursor+=1
                if cursor==len(lines):raise ValueError('Missing native raw state')
                cursor+=1;frame=parse(lines[start:cursor]);admissions+=1
                if frame['tick']!=phase*1000:raise ValueError('Wrong native observation time')
                events=frame['events']
                if label=='settled':
                    if events:raise ValueError('Deleted payload remains reachable')
                    continue
                if label=='queued':
                    if len(events)!=1:raise ValueError('Wrong admitted queue population')
                    e=events[0]
                    if e['region']!=('init' if phase==0 else 'active') or e['slot']!=(-1 if phase==0 else 0) or e['ordinal']!=0:raise ValueError('Wrong queue position')
                    if e['id']<=lifetime_max:raise ValueError('Reused event lifetime')
                    lifetime_max=e['id'];outer[phase]=e
                elif label=='inner':
                    if kind!='nested' or len(events)!=2:raise ValueError('Missing nested executing parent')
                    child,parent=events;nested_frames+=1
                    if child['region']!='executing' or child['slot']!=-2 or child['ordinal']!=0 or child['raw']!=bytes([0xb5])*80 or child['port']!=3:raise ValueError('Wrong nested payload')
                    if child['id']<=lifetime_max:raise ValueError('Wrong nested lifetime')
                    lifetime_max=child['id']
                    if targets.setdefault(1,child['target'])!=child['target']:raise ValueError('Nested target rebound')
                    if parent['ordinal']!=1:raise ValueError('Wrong executing parent depth')
                    events=[parent]
                else:
                    if label not in ('outer-before','outer-after') or len(events)!=1:raise ValueError('Wrong executing population')
                e=events[0];expected=dict(outer[phase])
                if label!='queued':expected.update(region='executing',slot=-2,ordinal=1 if label=='inner' else 0)
                if e!=expected:raise ValueError('Executing payload/identity changed')
                if e['raw']!=bytes([0x88])*9 or e['port']!=1 or targets.setdefault(0,e['target'])!=e['target']:raise ValueError('Wrong parent target/payload')
            expected_observations=[];expected_output=[]
            for phase in (0,1):
                has_child=kind=='nested' or phase==1 or timing=='early'
                expected_observations.extend([(phase,'queued'),(phase,'outer-before')])
                parent=f'AF_VALUE {phase*1000} {phase} 0 1 '+('88'*9)
                child=f'AF_VALUE {phase*1000} {phase} 1 3 '+('3d' if family==2 else 'b5')+'b5'*79
                private=[f'AF_PRIVATE {int(family==2)}'] if family else []
                if kind=='nested':
                    expected_observations.extend([(phase,'inner'),(phase,'outer-after')]);expected_output+=private+[child,parent]
                else:
                    expected_output.append(parent)
                    if has_child:expected_observations.append((phase,'inner'));expected_output+=private+[child]
                expected_observations.append((phase,'settled'))
            expected_output.append('finish')
            if ordinary!=expected_output:raise ValueError('Private subclass or original continuation changed')
            if observed!=(expected_observations if mode=='observe' else []):raise ValueError('Missing native lifecycle stage')
            if reference is None:reference=ordinary
            if ordinary!=reference:raise ValueError('Candidate differs from original execution')
    return dict(qualified=False,controlsPassed=True,refusals=refusals,admissions=admissions,nestedFrames=nested_frames,originalContinuationExactlyEqual=True,scope='Shared test adapter in original and candidate native runtimes constructs exact/subclass assignment objects. Early/late initialization and active queues plus executing subclasses refuse before output and refuse mutation without changing legacy payloads. Nested exact execution preserves child/parent lifetime, depth, bytes and destination identities; parent state survives child deletion. Private subclass inversion changes native output as independently expected.',notEstablished=['Operational board integration and cost','General rollback and freed-storage equivalence'])

def run(runtime,modules,out):
    runtime=runtime.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    builds={mode:json.loads((runtime/mode/'build.json').read_text()) for mode in ('original','candidate')}
    for mode,build in builds.items():
        for name,digest in build['outputs'].items():
            if sha(runtime/mode/name)!=digest:raise ValueError('Changed adapted runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/assignment_raw_native.{ext}',out/f'probe.{ext}')
    candidate=runtime/'candidate';flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[runtime/mode/'vvp/libvvp.so' for mode in builds]+[candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')];pins={str(p):sha(p) for p in paths};runs={}
    for kind,timing,family in CASES:
        for mode in ('original','disabled','observe'):
            lib=runtime/('original' if mode=='original' else 'candidate')/'vvp/libvvp.so';name=f'{kind}-{timing}-{family}-{mode}'
            env=dict(os.environ,K7658_AF_KIND=kind,K7658_AF_TIMING=timing,K7658_AF_FAMILY=str(family),K7658_AF_MODE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during native controls')
    for mode in builds:shutil.copy2(runtime/mode/'build.json',out/(mode+'-build.json'))
    sources={n:sha(HERE/n) for n in ('assignment_raw_native.py','assignment_raw.py','fixtures/assignment_raw_native.cc','fixtures/assignment_raw_native.v')}
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources=sources),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('runtime','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Native assignment admission and nested execution verified.')
    else:
        if not all((a.runtime,a.modules,a.out)):p.error('Need adapted runtime, modules and fresh output')
        run(a.runtime,a.modules,a.out)
