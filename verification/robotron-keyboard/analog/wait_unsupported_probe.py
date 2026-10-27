#!/usr/bin/env python3
"""Verify fail-closed observation of nonempty event-controlled assignment payloads."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    output={mode:(root/(mode+'.stdout')).read_text().splitlines() for mode in ('baseline','disabled','enabled','corrupt')}
    for mode in output:
        if (root/(mode+'.stderr')).read_text():raise ValueError('Unexpected simulator diagnostic')
    expected=['VWM_API 0 0','VWM_DONE 0','CONTINUED 1000','RESULT 7000 5a']
    if output['baseline'][:4]!=expected or len(output['baseline'])!=5 or '$finish called at 8000 (1ps)' not in output['baseline'][-1]:raise ValueError('Missing complete event-controlled assignment')
    disabled=output['disabled'].copy()
    if not disabled or disabled[0]!='VWM_API 0 1':raise ValueError('Missing candidate API')
    disabled[0]='VWM_API 0 0'
    if disabled!=output['baseline']:raise ValueError('Disabled candidate changed output')
    for mode in ('enabled','corrupt'):
        if output[mode]!=['VWM_API 0 1']:raise ValueError('Unsupported observation continued or emitted accepted state')
    return dict(completed=True,qualified=False,disabledOutputExactlyEqual=True,unsupportedStateRejectedBeforeContinuation=True,scope='Pending repeat-event assignment exercises nonempty event_ctls; observer refuses unsupported payloads. This is rejection coverage, not event-control serialization or rollback coverage.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/wait_probe.c' if ext=='c' else 'fixtures/wait_unsupported.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_WAIT_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode}
        if r.returncode!=(0 if name in ('baseline','disabled') else 2):raise ValueError('Wrong unsupported-state termination')
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('wait_unsupported_probe.py','fixtures/wait_probe.c','fixtures/wait_unsupported.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Nonempty event-control state is rejected before continuation.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
