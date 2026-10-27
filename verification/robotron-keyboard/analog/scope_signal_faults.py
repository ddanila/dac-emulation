#!/usr/bin/env python3
"""Verify native non-bridge toggles restore before original HDL continuation."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
from scope_signals import HERE,review as prior_review


def review(root):
    with tempfile.TemporaryDirectory() as tmp:
        filtered=Path(tmp);shutil.copy2(root/'run.json',filtered/'run.json')
        for mode in ('baseline','disabled','enabled'):
            lines=(root/(mode+'.stdout')).read_text().splitlines();toggles=[l for l in lines if l.startswith('TOGGLE ')]
            expected=[f'TOGGLE {r} {f} restored' for r in (1,2) for f in range(6)] if mode=='enabled' else []
            if toggles!=expected:raise ValueError('Missing native toggle/restoration')
            (filtered/(mode+'.stdout')).write_text('\n'.join(l for l in lines if not l.startswith('TOGGLE '))+'\n')
            shutil.copy2(root/(mode+'.stderr'),filtered/(mode+'.stderr'))
        prior=prior_review(filtered)
    return dict(qualified=False,controlsPassed=True,priorSignalControls=prior,nativeToggleRestorations=12,
        scope='Six exported non-bridge diagnostic toggles per round detect changes/refuse with zero output, preserve bridge admission and restore exactly before original/disabled/enabled HDL continuation. Static fixture; full transient and lifecycle qualification remain separate.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_signal_faults.{ext}',out/f'probe.{ext}')
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
