#!/usr/bin/env python3
"""Replay native port field faults with exact restoration and continuation."""
import argparse,json,os,platform,shutil,subprocess,copy
from pathlib import Path
from ttl7406_probe import sha
from port_payload import parse,HERE


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native port fault control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid port fault image')
                images[key]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected += [f'REFUSED {r} {field}' for field in range(3,9)]
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE 5 5','finish']:raise ValueError('Changed port fault continuation/refusal')
    keys=set()
    for r in (1,2):
        key=f'before{r}';keys.add(key);before=images.get(key)
        if not before or before['tick']!=r*1000 or len(before['ports'])!=2 or sum(bool(p['node']) for p in before['ports'])!=2:raise ValueError('Missing resolved port baseline')
        for field in range(9):
            key=f'restored{field}_{r}';keys.add(key)
            if images.get(key)!=before:raise ValueError('Port field restoration differs')
            if field<3:
                expected=copy.deepcopy(before);row=expected['ports'][0]
                if field==2:row['bits'][0]['index']^=1
                else:row[('index','direction')[field]]^=1
                key=f'changed{field}_{r}';keys.add(key)
                if images.get(key)!=expected:raise ValueError('Wrong native port field change')
    if set(images)!=keys:raise ValueError('Unexpected port fault image')
    return dict(qualified=False,controlsPassed=True,rounds=2,changedFields=['portIndex','portDirection','bitIndex'],
        refusedFields=['width','portParent','namePointer','netReference','bitParent','referenceReadiness'],
        exactRestorations=18,resolvedNonNullPortReferences=2,originalContinuationExactlyEqual=True,
        scope='Native diagnostic fields only. Every refusal has negative status and zero output; all fields restore before HDL continuation. Readiness is an injected false guard, not actual early-resolution execution. Static fixture; operational board and lifecycle qualification remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/port_payload_faults.{ext}',out/f'probe.{ext}')
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
