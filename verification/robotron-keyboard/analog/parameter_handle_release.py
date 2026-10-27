#!/usr/bin/env python3
"""Check public VPI parameter handle releases without claiming native deletion."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from parameter_payload import parse
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={};expected=[]
    for n in (1,2):
        expected.append(f'ROUND {n}')
        for name in ('P','W','R','S'):
            for api in (0,1):expected.append(f'RELEASE {n} test.{name} {api} 1 SAME')
    expected+=['CONTINUE 3 123456789abcdef01234 1.5','finish']
    if set(receipt['runs'])!={'none-'+m for m in ('baseline','disabled','enabled')}:raise ValueError('Missing release comparison')
    for mode in ('baseline','disabled','enabled'):
        key='none-'+mode;r=receipt['runs'][key]
        if r['exitCode'] or r['family']!='none' or r['observer']!=mode or (root/(key+'.stderr')).read_text():raise ValueError('Failed public release control')
        lines=(root/(key+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                label=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or label in images:raise ValueError('Invalid release image')
                images[label]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Missing release or changed original continuation')
    if set(images)!={'before1','after1','before2','after2'}:raise ValueError('Incomplete release inventory')
    for n in (1,2):
        before=images[f'before{n}']
        if before['tick']!=n*1000 or sorted(p['kind'] for p in before['rows'])!=['binary','binary','real','string']:raise ValueError('Wrong release population/time')
        if before!=images[f'after{n}']:raise ValueError('Release changed parameter inventory')
    later=copy.deepcopy(images['before1']);later['tick']=2000
    if later!=images['before2']:raise ValueError('Parameter state changed across resumed execution')
    return dict(qualified=False,controlsPassed=True,parameters=4,releaseCallsPerRun=16,exactInventoryPreservations=16,originalVpiAndHdlContinuationExactlyEqual=True,
        scope='Two rounds of vpi_free_object and vpi_release_handle on four scope-owned binary/wide/real/string parameters return success while preserving handle identity, owner, size, VPI values and exact native inventory. Original/disabled/enabled HDL continuation matches. These public APIs suppress deletion for these classes; native destruction, address reuse, teardown and general lifecycle qualification remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_handle_release.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for family in ('none',):
        for mode in ('baseline','disabled','enabled'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,ROBOTRON_PARAMETER_CLASS=family,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            (out/(family+'-'+mode+'.stdout')).write_text(r.stdout);(out/(family+'-'+mode+'.stderr')).write_text(r.stderr);runs[family+'-'+mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib),family=family,observer=mode);r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
