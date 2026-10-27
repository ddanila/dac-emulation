#!/usr/bin/env python3
"""Verify unsupported native reduction families refuse without emitting partial state."""
import argparse,json,os,platform,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
FAMILIES=('derived-nor','derived-base')


def review(root):
    from reduction_family_probe import review as family_review
    from reduction_delta_probe import block,image
    from reduction_probe import parse
    result=family_review(root)
    for family in FAMILIES:
        lines=(root/(family+'.reference')).read_text().splitlines();frame,end=block(lines)
        if end!=len(lines) or frame['mode']!='R' or frame['tick']!=0:raise ValueError('Invalid admitted reference')
        state=parse(image(frame['tick'],frame['rows']))
        if len(state['nodes'])!=1:raise ValueError('Reference must precede unsupported allocation')
        node=state['nodes'][0]
        if node['kind']!=5 or node['bits']!='':raise ValueError('Wrong admitted constructor state')
    result.update(referenceCreatedBeforeUnsupportedAllocation=True,refusedAPIs=['dense','reference-reset','delta'])
    result['scope']='A valid NOR-only reference precedes unsupported behavior-changing subclass allocation. Dense inventory and delta refuse before output. Repeated reference creation also refuses, preserving its one-reference lifecycle rule. Original and disabled continuations remain equal.'
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/reduction_delta_family.cc' if ext=='cc' else 'fixtures/reduction_family.v'),out/('probe.'+ext))
    commands=[]
    for family in FAMILIES:
        command=['iverilog','-g2012','-o',str(out/(family+'.vvp')),str(out/'probe.v')]
        commands.append(command);subprocess.run(command,check=True)
    # Extract declarations from the verified native source; reductions have no public header.
    source=(candidate/'vvp/reduce.cc').read_text();declarations=[]
    for name in ('base','and','or','xor','nand','nor','xnor'):
        marker='class vvp_reduce_'+name+' '
        start=source.index(marker);end=source.index('};',start)+2
        declarations.append(source[start:end])
    (out/'reduction_fixture.h').write_text('#include "vvp_net.h"\n'+'\n'.join(declarations)+'\n')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    command=['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')];commands.append(command);subprocess.run(command,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'reduction_fixture.h',*modules.glob('*.vpi')]};runs={}
    for family in FAMILIES:
        for mode in ('baseline','disabled','observe'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,K7658_REDUCTION_FAMILY=family,K7658_REDUCTION_MODE='off' if mode in ('baseline','disabled') else mode)
            env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',family+'.vvp']
            r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30);name=family+'-'+mode
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
            runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Runtime changed during probe')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('reduction_delta_family.py','reduction_delta_probe.py','reduction_probe.py','reduction_family_probe.py','net_types_probe.py','net_probe.py','fixtures/reduction_delta_family.cc','fixtures/reduction_family.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('candidate','baseline','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Unsupported reduction families refused without partial inventory.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
