#!/usr/bin/env python3
"""Native zero-output refusal controls for initialized scope-pointer admission."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
EXPECTED=[]
for round_id in (1,2):
    EXPECTED += [f'ROUND {round_id}', 'REFUSED root','REFUSED intern','REFUSED parent','REFUSED missing-child',f'RESTORED {round_id}']
EXPECTED += ['CONTINUE 5 2','finish']


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native scope admission control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and not lines[i].startswith('VSC_END '):i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid scope image')
                i+=1;images[key]=lines[start:i];continue
            events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=EXPECTED:raise ValueError('Changed native continuation: '+str(events))
    if set(images)!={'before1','restored1','before2','restored2'}:raise ValueError('Missing native witnesses')
    for i in (1,2):
        before=images[f'before{i}']
        if before!=images[f'restored{i}'] or before[0]!=f'VSC_BEGIN 1 {i*1000}' or not any(l.startswith('VSC_SCOPE ') for l in before):raise ValueError('Changed restoration/binding')
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,
        refusedFaults=['foreign root pointer','foreign intern pointer','foreign parent pointer','omitted registered child'],rounds=2,
        scope='Native initialized-scope/internal-object registry guards the existing static walker. Eight refusal checks require negative status and zero output before restoration. Original, disabled and enabled runs preserve HDL continuation. No metadata payload, scope deletion/address reuse, new runtime allocation family or operational board qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_admission.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_SCOPE_ADMISSION='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
