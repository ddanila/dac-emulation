#!/usr/bin/env python3
"""Review native parameter allocation after a complete initial inventory."""
import argparse,copy,json,os,platform,shutil,struct,subprocess
from pathlib import Path
from ttl7406_probe import sha
from parameter_payload import parse
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    if set(receipt['runs'])!={'baseline','disabled','enabled'}:raise ValueError('Missing growth comparisons')
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native growth failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                label=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or label in images:raise ValueError('Invalid growth image')
                images[label]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for n in (1,2):
            expected.append(f'ROUND {n}')
            if mode!='baseline':expected += [f'REFUSED {n}']+[f'ADDED {n} {k}' for k in range(3)]
        if events!=expected+['CONTINUE 3 123456789abcdef01234 1.5','finish']:raise ValueError('Missing growth or changed continuation')
    labels={f'before{n}' for n in (1,2)}|{f'after{n}_{k}' for n in (1,2) for k in range(3)}
    if set(images)!=labels or len(images['before1']['rows'])!=4:raise ValueError('Missing full growth coverage')
    previous=None
    for n in (1,2):
        before=images[f'before{n}']
        if before['tick']!=n*1000:raise ValueError('Wrong growth time')
        if previous is not None:
            expected=copy.deepcopy(previous);expected['tick']=n*1000
            if before!=expected:raise ValueError('Growth state changed across continuation')
        for kind in range(3):
            after=images[f'after{n}_{kind}'];old=before['rows'];rows=after['rows']
            if after['tick']!=before['tick'] or len(rows)!=len(old)+1 or rows[:-1]!=old:raise ValueError('Growth changed existing parameter state')
            row=rows[-1];serial=3*(n-1)+kind+1
            if row['id']<=max(p['id'] for p in old) or row['pointer'] in {p['pointer'] for p in old} or row['scope']!=old[0]['scope'] or row['kind']!=('binary','real','string')[kind] or bytes.fromhex(row['name'])!=f'__growth_{kind}_{serial}\0'.encode():raise ValueError('Invalid fresh parameter identity')
            v=row['value']
            if kind==0:
                if v['width']!=80 or v['signed'] or v['sized']:raise ValueError('Wrong grown binary shape')
                for bit in range(80):
                    a,b=v['words'][bit//v['wordBits']];mask=1<<(bit%v['wordBits'])
                    if not a&mask or bool(b&mask)!=(bit!=0):raise ValueError('Wrong grown binary value')
            elif kind==1 and v['value']!=struct.pack('=d',2.5).hex():raise ValueError('Wrong grown real value')
            elif kind==2 and v['value']!='47005200':raise ValueError('Lost grown embedded-null string')
            before=after
        previous=before
    return dict(qualified=False,controlsPassed=True,initialParameters=4,finalParameters=10,newParameters=6,rounds=2,unknownKindRefusals=2,originalHdlContinuationExactlyEqual=True,
        scope='Test-only native allocation adds exact binary/real/string parameters through registration and normal scope attachment after the first full inventory, twice. Fresh increasing IDs and distinct live pointers, unchanged earlier rows, complete payloads and original/disabled/enabled HDL continuation are checked. Destruction/reuse, unsupported late classes, compact growth and operational board admission remain separate.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_growth.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
