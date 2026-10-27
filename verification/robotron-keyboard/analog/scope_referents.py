#!/usr/bin/env python3
"""Native counterexamples to treating scope membership as metadata/referent coverage."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
EXPECTED=['BASE 1.000','UNITS 0.001','LINE_CHANGED 17','LOOKUP_MISSING 1','RESTORED 1','CONTINUE 5 2.000','finish']


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed scope control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and not lines[i].startswith('VSC_END '):i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid scope image')
                i+=1;image=lines[start:i]
                if not image or image[0]!='VSC_BEGIN 1 1000' or not any(x.startswith('VSC_SCOPE ') for x in image):raise ValueError('Missing scope binding')
                images[key]=image;continue
            events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=EXPECTED:raise ValueError('Changed native behavior: '+str(events))
    if set(images)!={'before','units','line','intern'} or any(v!=images['before'] for v in images.values()):raise ValueError('Scope membership image changed or missing')
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,
        uncoveredFields=['scope time_units','scope lineno','scope intern ordered object membership'],
        scope='Actual native field mutations change scaled VPI time, source-line metadata and named signal lookup while the complete scope hierarchy/thread-membership image stays identical. Every mutation is restored before HDL continuation. Baseline, disabled and observed runs have identical visible behavior. Counterexamples only; no complete metadata observer or board qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_referents.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_SCOPE_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
