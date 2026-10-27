#!/usr/bin/env python3
"""Native signal-handle families, range/cache mappings and late admission."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from signal_handles import parse
from net_probe import pointer
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PROFILE={
 'r':('10signal_reg',3,0,1),
 'n':('10signal_net',0,3,0),
 'number':('14signal_integer',31,0,1),
 'wide':('10signal_reg',70,-2,0),
 'negative':('10signal_reg',2,-1,0),
 'single':('10signal_reg',0,0,0),
 'late':('10signal_net',3,0,0),
}
REJECT=['two-state','real','array','array-word','constant','null','foreign']


def expected_events():
    events=[]
    for stage in range(4):
        values=dict(r=5 if stage==3 else 10,n=5 if stage==3 else 10,number=-33 if stage==3 else -17,wide=1 if stage==3 else (1<<72)|1,negative=6,single=1,late=5 if stage==3 else 10)
        count=6 if stage<2 else 7
        for name in (list(PROFILE)[:6] if stage==1 else ['late'] if stage==3 else []):
            if name=='number':events.append(f'NO_BITS {stage} number');continue
            _,left,right,_=PROFILE[name];width=abs(left-right)+1;value=values[name]
            events.append(f'ENDS {stage} {name} {(value>>(width-1))&1} {value&1}')
        for name in list(PROFILE)[:count]:
            _,left,right,_=PROFILE[name];width=abs(left-right)+1;value=values[name]&((1<<width)-1)
            events.append(f'VALUE {stage} {name} {value:0{width}b}')
        events.append(f'DONE {stage}')
    return events+['CONTINUE 5 -33 1','finish']


def review(root):
    runs=json.loads((root/'run.json').read_text())['runs'];images={};bindings={}
    for mode in ('baseline','disabled','enabled'):
        if runs[mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native family run')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[];rejections=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('BIND '):
                a=line.split()
                if len(a)!=4 or mode!='enabled' or a[1] in bindings or a[1] not in PROFILE:raise ValueError('Invalid handoff')
                bindings[a[1]]=(int(a[2]),pointer(a[3]));continue
            if line.startswith('REJECT '):rejections.append(line);continue
            if line.startswith('IMAGE '):
                stage=int(line.split()[1]);start=i
                while i<len(lines) and not lines[i].startswith('VSH_END '):i+=1
                if i==len(lines) or mode!='enabled' or stage in images:raise ValueError('Invalid native image')
                i+=1;images[stage]=parse(lines[start:i]);continue
            events.append('finish' if '$finish called at 5000 (1ps)' in line else line)
        if events!=expected_events():raise ValueError('Changed native value/range continuation')
        expected=[f'REJECT {stage} {name}' for stage in (0,3) for name in REJECT] if mode=='enabled' else []
        if rejections!=expected:raise ValueError('Missing unsupported family refusal')
    if set(bindings)!=set(PROFILE) or set(images)!=set(range(4)):raise ValueError('Missing handoff/stages')
    if len({b[0] for b in bindings.values()})!=7 or len({b[1] for b in bindings.values()})!=7:raise ValueError('Reused handle identities')
    if bindings['late'][0]<=max(v[0] for k,v in bindings.items() if k!='late'):raise ValueError('Late handle reused identity')
    previous={}
    for stage,state in images.items():
        if state['tick']!=[1000,2000,3000,5000][stage]:raise ValueError('Changed native time')
        names=list(PROFILE)[:6 if stage<2 else 7];rows={r['id']:r for r in state['rows']}
        if set(rows)!={bindings[n][0] for n in names}:raise ValueError('Changed admitted population')
        current={}
        for name in names:
            row=rows[bindings[name][0]];kind,left,right,signed=PROFILE[name];count=abs(left-right)+1
            if (row['pointer'],row['kind'],row['msb'],row['lsb'],row['signed'])!=(bindings[name][1],kind,left,right,signed):raise ValueError('Changed typed metadata')
            if bytes.fromhex(row['name'])!=name.encode()+b'\0':raise ValueError('Changed native name')
            allocated=(stage>=1 and name not in ('late','number')) or (stage==3 and name=='late')
            if row['count']!=(count if allocated else 0):raise ValueError('Unexpected cache allocation')
            expected=[right+i if left>=right else right-i for i in range(count)] if allocated else []
            if [b['value'] for b in row['cache']]!=expected:raise ValueError('Incorrect native bit-index mapping')
            if name in previous:
                old=copy.deepcopy(previous[name]);new=copy.deepcopy(row)
                if stage==1 or name=='late' and stage==3:
                    for key in ('bits','count','cache'):old.pop(key);new.pop(key)
                if new!=old:raise ValueError('Changed existing handle lifetime/cache')
            current[name]=row
        if stage>=2:
            for key in ('node','nodeId','scope','scopeId'):
                if current['late'][key]!=current['r'][key]:raise ValueError('Lost explicit native alias binding')
        previous=current
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,
                scope='Native reg, net and integer handle metadata with scalar, ascending, descending, negative and 73-bit ranges; existing bit caches preserve normalized index mappings. Explicit late native net construction/admission gets a fresh handle identity while sharing a live node. Unsupported two-state, real, array, array-word, constant and foreign handles refuse admission before and after growth without changing admitted state. No board-created alias, handle deletion, automatic-scope admission or operational qualification is inferred.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/signal_handle_families.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
