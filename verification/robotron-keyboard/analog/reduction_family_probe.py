#!/usr/bin/env python3
"""Verify unsupported native reduction families refuse without emitting partial state."""
import argparse,json,os,platform,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
FAMILIES=('derived-nor','derived-base')


def review(root):
    from net_types_probe import parse
    receipt=json.loads((root/'run.json').read_text())
    classes={'derived-nor':'ExtraNor','derived-base':'ExtraReduction'}
    observed={}
    for family in FAMILIES:
        native=parse((root/(family+'.types')).read_text().splitlines())
        kinds={n['funClass'] for n in native['nodes'] if n['fun']}
        if classes[family] not in kinds or 'vvp_reduce_nor' not in kinds:raise ValueError('Missing unsupported and admitted native families')
        observed[family]=sorted(kinds)
        reference=None
        for mode in ('baseline','disabled','observe'):
            name=family+'-'+mode;lines=(root/(name+'.stdout')).read_text().splitlines()
            if (root/(name+'.stderr')).read_text():raise ValueError('Unexpected family diagnostic')
            if mode=='observe':
                if receipt['runs'][name]['exitCode']!=2 or lines!=['FAMILY_PRESENT '+family,'REDUCTION_REFUSED']:raise ValueError('Unsupported reduction accepted or partial inventory emitted')
            else:
                expected=['FAMILY_PRESENT '+family,'FAMILY_VALUE 1000 0 1','FAMILY_VALUE 1000 1 '+('0' if family=='derived-nor' else '1')]
                if receipt['runs'][name]['exitCode']!=0 or len(lines)!=4 or lines[:-1]!=expected or '$finish called at 2000 (1ps)' not in lines[-1]:raise ValueError('Invalid family continuation')
                if reference is None:reference=lines
                elif reference!=lines:raise ValueError('Disabled reduction observer changed continuation')
    return dict(qualified=False,controlsPassed=True,unsupportedProfilesRefused=list(FAMILIES),noPartialInventory=True,disabledContinuationExactlyEqual=True,nativeClasses=observed,
        scope='Native NOR and direct reduction-base subclasses with private output-inversion fields are rejected alongside an admitted NOR, before any inventory output. Original and disabled continuation preserve the subclass behavior.',
        notEstablished=['Payload support for rejected classes','Every possible plugin-defined subclass','Board integration and full qualification'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/reduction_family.'+ext),out/('probe.'+ext))
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
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('reduction_family_probe.py','net_types_probe.py','net_probe.py','fixtures/reduction_family.cc','fixtures/reduction_family.v')}),indent=2)+'\n')
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
