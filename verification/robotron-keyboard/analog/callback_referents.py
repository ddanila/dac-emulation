#!/usr/bin/env python3
"""Native counterexamples to treating callback object identity as referent coverage."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from callback_list_probe import parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
EXPECTED=['BASE -6','NODE 3','SIGNED 10','RANGE 0 3','RESTORED -6','BIT 0','CALLBACK 5','CONTINUE 5 3','finish']


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native referent control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and not lines[i].startswith('VCL_END '):i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid referent image')
                i+=1;images[key]=parse(lines[start:i]);continue
            events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=EXPECTED:raise ValueError('Changed native referent behavior')
    if set(images)!={'before','node','signed','range','bit-cache'}:raise ValueError('Missing referent witness')
    if any(v!=images['before'] for v in images.values()):raise ValueError('Callback list changed in referent witness')
    callbacks=[c for o in images['before']['owners'] for c in o['callbacks']]
    if len(callbacks)!=1 or images['before']['tick']!=1000:raise ValueError('Unbound callback witness')
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,
                uncoveredReferents=['signal node pointer','signed flag','range constants','lazy bit-handle cache'],
                scope='Native signal referents change VPI behavior or allocate persistent bit handles while the admitted callback list image stays identical. Mutated fields restore before HDL continuation; original, disabled and observed runs agree. This demonstrates missing referent coverage, not a completed observer or board qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/callback_referents.{ext}',out/f'probe.{ext}')
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
