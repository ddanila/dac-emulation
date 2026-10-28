#!/usr/bin/env python3
"""Check public VPI memory handle releases without claiming native deletion."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    expected=[]
    for n in (1,2):
        expected.append(f'ROUND {n}')
        for name in ('test.mem','test.mem[0]','test.mem[1]'):
            for api in (0,1):expected.append(f'RELEASE {n} {name} {api} 1 SAME')
    expected+=['CONTINUE 35 70','finish']
    if set(receipt['runs'])!={'none-'+m for m in ('baseline','disabled','enabled')}:raise ValueError('Missing release comparison')
    for mode in ('baseline','disabled','enabled'):
        key='none-'+mode;r=receipt['runs'][key]
        if r['exitCode'] or r['family']!='none' or r['observer']!=mode or (root/(key+'.stderr')).read_text():raise ValueError('Failed release control')
        lines=(root/(key+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                label=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or label in images:raise ValueError('Invalid image')
                images[label]=lines[start:i];i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Missing release or changed continuation')
    if set(images)!={'before1','after1','before2','after2'}:raise ValueError('Missing inventory')
    for n in (1,2):
        before=images[f'before{n}']
        if before!=images[f'after{n}'] or before[0]!=f'VMM_BEGIN 1 {n*1000}' or 'VMM_END 1' not in before or not any(x.startswith('VAR_BEGIN ') for x in before):raise ValueError('Changed or missing memory inventory')
    return dict(qualified=False,controlsPassed=True,releaseCallsPerRun=12,rounds=2,originalVpiAndHdlContinuationExactlyEqual=True,scope='Public release of one static memory and two materialized word handles preserves identity, values, owner and native metadata/array images across writes. Public release is not native destruction, teardown or address-reuse qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/memory_handle_release.{ext}',out/f'probe.{ext}')
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
