#!/usr/bin/env python3
"""Native port-bit payload counterexamples to scope identity-only observation."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={};expected=[]
    for i in (1,2):expected += [f'ROUND {i}','ORDER before 0 1 2 3','ORDER swapped 1 0 2 3',f'RESTORED {i}']
    expected += ['CONTINUE 5 5','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native port control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid port witness image')
                image=lines[start:i];i+=1
                split=next((j for j,l in enumerate(image) if l.startswith('VSMR_BEGIN ')),None)
                if split is None:raise ValueError('Missing reference witness')
                metadata=metadata_parse(image[:split]);reference=reference_parse(image[split:])
                if metadata['tick']!=reference['tick']:raise ValueError('Witness time mismatch')
                images[key]=image
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Changed native port iteration or continuation')
    if set(images)!={f'{kind}{i}' for i in (1,2) for kind in ('before','swapped','foreign','restored')}:raise ValueError('Missing port witnesses')
    for i in (1,2):
        before=images[f'before{i}']
        if before[0]!=f'VSM_BEGIN 1 {i*1000}' or any(images[f'{kind}{i}']!=before for kind in ('swapped','foreign','restored')):raise ValueError('Scope identity images changed')
    return dict(qualified=False,controlsPassed=True,rounds=2,originalContinuationExactlyEqual=True,
        portIterationOrderChanges=True,scopeMetadataAndReferencesExactlyUnchanged=True,
        foreignBitPointerNotDereferenced=True,
        scope='Injected port-bit order change affects native VPI iteration while complete scope metadata/reference images remain equal. A foreign port-bit pointer is likewise invisible to those images and is restored without dereferencing. Both rounds restore native iteration and preserve original-runtime HDL continuation. No ordinary board mutation, port payload coverage, ownership/lifecycle or operational qualification is claimed.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/port_referents.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_PORT_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
