#!/usr/bin/env python3
"""Compare native dense and compact arrays through memory allocation."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    import tempfile
    from array_compact_probe import separate
    from memory_growth import review as native_review
    counts=[];dense_bytes=compact_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for name in ('run.json','build.json','baseline.stdout','baseline.stderr','disabled.stdout','disabled.stderr','enabled.stdout','enabled.stderr'):
            shutil.copyfile(root/name,copied/name)
        for mode in ('baseline','disabled','enabled'):
            target=copied/(mode+'.stdout');lines,n,full,compact=separate(target.read_text().splitlines())
            counts.append(n);dense_bytes+=full;compact_bytes+=compact
            target.write_text('\n'.join(lines)+'\n')
        native=native_review(copied)
    if counts!=[0,0,10]:raise ValueError('Missing compact growth images')
    if json.loads((root/'build.json').read_text())!=json.loads((HERE/'reports/memory-growth/build.json').read_text()):raise ValueError('Changed growth runtime')
    return dict(qualified=False,controlsPassed=True,nativeGrowth=native,matchedSnapshots=10,denseBytes=dense_bytes,compactBytes=compact_bytes,scope='Ten newly executed native dense/compact pairs reconstruct every array byte while four memories and their lazy caches are allocated. Includes high X bits, declared ranges, complete word-cache parent/word ownership and original/disabled continuation. Does not qualify destruction, reuse, metadata delta logging or continuous board observation.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/memory_growth_compact.{ext}',out/f'probe.{ext}')
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
