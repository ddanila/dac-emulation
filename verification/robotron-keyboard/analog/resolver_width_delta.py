#!/usr/bin/env python3
"""Qualify compact resolver capture across single-input and width boundaries."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
import resolver_widths as dense
from resolver_delta_probe import separate
HERE=Path(__file__).resolve().parent
WIDTHS=dense.WIDTHS


def review(root):
    count=full_bytes=delta_bytes=reference_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for mode in ('baseline','disabled','enabled','corrupt'):
            lines,n,full,delta,reference=separate(dense.output_text(root,mode).splitlines())
            (copied/(mode+'.stdout')).write_text('\n'.join(lines)+'\n' if lines else '')
            count+=n;full_bytes+=full;delta_bytes+=delta;reference_bytes+=reference
        result=dense.review(copied)
    if not count or min(delta_bytes,reference_bytes,full_bytes)<=0:raise ValueError('Missing resolver delta evidence')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    result['notEstablished']=['Additional raw-strength input combinations and partial-first initialization','Operational board integration','Freed storage or general rollback']
    return result


def run(candidate,baseline,modules,out,width):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/resolver_width_delta.cc' if ext=='cc' else 'fixtures/resolver_probe.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11','-DPROBE_WIDTH='+str(width),*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_RESOLVER_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(width=width,commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('resolver_width_delta.py','resolver_widths.py','resolver_delta_probe.py','resolver_probe.py','resolver_source_contract.py','net_probe.py','fixtures/resolver_width_delta.cc','fixtures/resolver_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


def review_all(root):
    results={str(width):review(root/('width-'+str(width))) for width in WIDTHS}
    return dict(qualified=False,controlsPassed=True,widths=list(WIDTHS),profiles=results,
                scope='Exact compact reconstruction through single-input pull aliasing, clipped partial writes and vector storage boundaries, with independent cache/output and original-runtime continuation controls. Operational board integration remains open.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review_all(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed width assessment')
        print('Resolver width and single-input controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        a.out.mkdir(exist_ok=False)
        for width in WIDTHS:run(a.candidate,a.baseline,a.modules,a.out/('width-'+str(width)),width)
        (a.out/'assessment.json').write_text(json.dumps(review_all(a.out),indent=2)+'\n')
