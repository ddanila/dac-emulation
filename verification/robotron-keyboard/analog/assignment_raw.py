#!/usr/bin/env python3
"""Validate exact pending/executing strength-assignment payloads."""
import argparse,copy,json,lzma,os,platform,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from assignment_probe import parse_snapshot as legacy_parse
from wire_raw_probe import triplet
HERE=Path(__file__).resolve().parent
WIDTHS=(0,1,8,9,80)
VALUES=bytes.fromhex('00888190b5d3e7f61267a9feff77ee66')

def parse(lines):
    if len(lines)<2 or not re.fullmatch(r'VAR_BEGIN 1 [0-9]+',lines[0]):raise ValueError('Invalid assignment raw header')
    tick=int(lines[0].split()[2]);events=[];ids=set();addresses=set();positions=set()
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=10 or a[0]!='VAR_EVENT':raise ValueError('Invalid raw assignment row')
        slot,ordinal,identity,port,width=map(int,(a[1],a[3],a[4],a[7],a[8]));region=a[2]
        valid=(slot==-2 and region=='executing') or (slot==-1 and region in ('init','final')) or (slot>=0 and region in ('start','active','inactive','nbassign','rwsync','rosync','del_thr'))
        if not valid or min(ordinal,width)<0 or identity<1 or port not in range(4):raise ValueError('Invalid raw assignment metadata')
        if any(not re.fullmatch(r'0x[0-9a-f]+',p) or int(p,16)==0 for p in a[5:7]):raise ValueError('Missing native pointer')
        if identity in ids or a[5] in addresses or (slot,region,ordinal) in positions:raise ValueError('Aliased event ownership')
        ids.add(identity);addresses.add(a[5]);positions.add((slot,region,ordinal))
        if (not width and a[9]!='-') or (width and (len(a[9])!=2*width or not re.fullmatch('[0-9a-f]+',a[9]))):raise ValueError('Incomplete raw payload')
        events.append(dict(slot=slot,region=region,ordinal=ordinal,id=identity,address=a[5],target=a[6],port=port,raw=bytes.fromhex(a[9]) if width else b''))
    if lines[-1]!=f'VAR_END {len(events)}':raise ValueError('Incomplete raw assignment inventory')
    return dict(tick=tick,events=events)


def bind(raw,legacy):
    expected=[]
    for event in raw['events']:
        if event['region']=='executing':continue
        row={k:event[k] for k in ('slot','region','ordinal','id','target','port')}
        row.update(kind=8,base=0,width=0,size=len(event['raw']),bits=''.join(triplet(x) for x in event['raw']) or '-')
        expected.append(row)
    if raw['tick']!=legacy['tick'] or expected!=[e for e in legacy['events'] if e['kind']==8]:raise ValueError('Legacy assignment binding mismatch')


def mutation(before,identity,op):
    result=copy.deepcopy(before);event=next(e for e in result['events'] if e['id']==identity);value=bytearray(event['raw'])
    if op<2 and (not value or op==1 and not any(x in (0,136) for x in value)):return None
    if op==2:value=bytearray(len(value)+1)
    elif op==3:event['port']^=1
    else:
        i=next(i for i,x in enumerate(value) if x in (0,136)) if op==1 else 0
        value[i]=value[i]^136 if op==1 else 102 if value[i]==238 else 238
    event['raw']=bytes(value);return result


def expected_value(phase,index):return bytes(VALUES[(phase+k)%len(VALUES)] for k in range(WIDTHS[index]))


def output_text(root,mode):
    p=root/(mode+'.stdout')
    return p.read_text() if p.exists() else lzma.open(str(p)+'.xz','rt').read()


def review(root):
    receipt=json.loads((root/'run.json').read_text());observations=0;faults={};reference=None
    expected_output=[f'ARM_VALUE {phase*1000} {phase} {index} {index%4} '+(expected_value(phase,index).hex() or '-') for phase in range(16) for index in range(5)]+['finish']
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native runtime failed')
        lines=output_text(root,mode).splitlines();cursor=stage=0;ordinary=[];targets={};previous_max=0;phase_events=[]
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot(raw=True):
            nonlocal cursor
            start=cursor;end='VAR_END ' if raw else 'VAP_END '
            while cursor<len(lines) and not lines[cursor].startswith(end):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated raw assignment observation')
            cursor+=1;return parse(lines[start:cursor]) if raw else legacy_parse(lines[start:cursor])
        while cursor<len(lines):
            if not lines[cursor].startswith('ARM_STAGE '):
                line=lines[cursor];ordinary.append('finish' if '$finish called at 16000 (1ps)' in line else line);cursor+=1;continue
            phase,position=divmod(stage,7);callback=position if position<6 else -1
            consume(f'ARM_STAGE {stage} {phase} {callback} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('ARM_BEFORE');before=snapshot();legacy=snapshot(False);bind(before,legacy)
                if before['tick']!=phase*1000:raise ValueError('Wrong native time')
                if position==0:
                    phase_events=copy.deepcopy(before['events'])
                    if len(phase_events)!=5:raise ValueError('Missing queued payload')
                    if any(e['id']<=previous_max for e in phase_events):raise ValueError('Reused lifetime identity')
                    previous_max=max(e['id'] for e in phase_events)
                    for index,e in enumerate(phase_events):
                        if targets.setdefault(index,e['target'])!=e['target'] or e['port']!=index%4 or e['raw']!=expected_value(phase,index):raise ValueError('Wrong native target/port/payload')
                        if e['region']!=('init' if phase==0 else 'active') or e['slot']!=(-1 if phase==0 else 0):raise ValueError('Wrong native queue')
                expected=[]
                if position<6:
                    for ordinal,e in enumerate(phase_events[position:]):
                        row=copy.deepcopy(e);row['ordinal']=ordinal;expected.append(row)
                    if position:
                        row=copy.deepcopy(phase_events[position-1]);row.update(slot=-2,region='executing',ordinal=0);expected.append(row)
                if before['events']!=expected:raise ValueError('Pending/executing lifetime or payload mismatch')
                consume('ARM_REPEAT')
                if snapshot()!=before:raise ValueError('Observation changed state')
                observations+=1
                if mode=='corrupt':
                    for e in before['events']:
                        for op in range(4):
                            changed=mutation(before,e['id'],op)
                            if changed is None:continue
                            consume(f"ARM_CHANGED {e['id']} {op}");actual=snapshot();old=snapshot(False);bind(actual,old)
                            if actual!=changed:raise ValueError('Wrong fault or unrelated state change')
                            if op==1 and old!=legacy:raise ValueError('Raw collision visible to legacy observer')
                            consume('ARM_RESTORED')
                            if snapshot()!=before:raise ValueError('Fault restoration failed')
                            key=('executing' if e['region']=='executing' else 'pending')+':'+str(op);faults[key]=faults.get(key,0)+1
            consume(f'ARM_DONE {stage}');stage+=1
        if stage!=112 or ordinary!=expected_output:raise ValueError('Original continuation values/times changed')
        if reference is None:reference=ordinary
        if ordinary!=reference:raise ValueError('Candidate changed original continuation')
    if set(faults)!={region+':'+str(op) for region in ('pending','executing') for op in range(4)}:raise ValueError('Missing fault ownership controls')
    return dict(qualified=False,controlsPassed=True,observations=observations,faultsByOwnership=faults,originalContinuationExactlyEqual=True,scope='Exact native initialization and active strength-vector assignment bytes, destination ports, event lifetimes and synchronous executing payloads. Widths include empty, 1, 8, 9 and 80; inputs include asymmetric strengths and 00/88 collisions. Targeted byte/collision/width/port faults restore before continuation.',notEstablished=['Native unsupported-subclass refusal controls','Nested synchronous assignment execution','Compact encoding and operational combined board integration','General rollback or freed-storage equivalence'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/assignment_raw.'+ext),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ASSIGNMENT_RAW=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('assignment_raw.py','assignment_probe.py','wire_raw_probe.py','net_probe.py','fixtures/assignment_raw.cc','fixtures/assignment_raw.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Raw assignment payload controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
