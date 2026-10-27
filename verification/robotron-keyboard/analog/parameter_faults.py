#!/usr/bin/env python3
"""Replay exact parameter metadata changes and guarded native pointer refusals."""
import argparse,json,os,platform,shutil,subprocess,copy
from pathlib import Path
from ttl7406_probe import sha
from parameter_payload import HERE,parse


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native parameter fault failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid parameter fault image')
                images[key]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected += [f'REFUSED {r} {f}' for f in range(9,16)]
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE 3 123456789abcdef01234 1.5','finish']:raise ValueError('Changed parameter fault continuation/refusal')
    keys=set()
    for r in (1,2):
        key=f'before{r}';keys.add(key);before=images.get(key)
        if not before or before['tick']!=r*1000 or len(before['rows'])!=4:raise ValueError('Missing parameter baseline')
        if sorted(p['kind'] for p in before['rows'])!=['binary','binary','real','string']:raise ValueError('Missing native parameter families')
        for field in range(16):
            key=f'restored{field}_{r}';keys.add(key)
            if images.get(key)!=before:raise ValueError('Parameter restoration differs')
            if field<9:
                expected=copy.deepcopy(before);kind='real' if field==7 else 'string' if field==8 else 'binary'
                row=next(p for p in expected['rows'] if p['kind']==kind);value=row['value']
                if field==0:value['words'][0][0]^=1
                elif field in (1,2):value['signed' if field==1 else 'sized']^=1
                elif field in (3,4,5):row[('local','file','line')[field-3]]^=1
                elif field==6:
                    data=bytearray.fromhex(row['name']);data[0]^=1;row['name']=data.hex()
                else:
                    data=bytearray.fromhex(value['value']);data[0]^=1;value['value']=data.hex()
                key=f'changed{field}_{r}';keys.add(key)
                if images.get(key)!=expected:raise ValueError('Wrong isolated parameter fault')
    if set(images)!=keys:raise ValueError('Unexpected parameter fault image')
    return dict(qualified=False,controlsPassed=True,rounds=2,exactRestorations=32,originalContinuationExactlyEqual=True,
        changedFields=['binaryWord','signed','sized','local','file','line','nameBytes','realBytes','stringBytes'],
        refusedFields=['binaryWidth','scopePointer','namePointer','wideAPointer','wideBPointer','stringPointer','stringLength'],
        scope='Sixteen native diagnostic fields per round either produce exactly the selected raw value/metadata change or refuse with negative status and zero bytes. All restore before original/disabled/enabled HDL continuation. Wide storage and embedded-null strings are included. Unsupported subclasses, lifecycle changes and operational board fault qualification remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_faults.{ext}',out/f'probe.{ext}')
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
