#!/usr/bin/env python3
"""Verify unsupported raw-wire filter classes refuse without emitting partial state."""
import argparse,json,os,platform,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
FAMILIES=('derived4','derived8','real')
CASES=tuple((family,phase) for family in FAMILIES for phase in ('early','late'))


def review(root):
    from net_types_probe import parse as parse_types
    from wire_raw_probe import parse as parse_raw
    receipt=json.loads((root/'run.json').read_text());refusals=0
    classes={'derived4':'ExtraWire4','derived8':'ExtraWire8','real':'vvp_wire_real'}
    for family,phase in CASES:
        for stage in (0,1,3,2,4):
            native=parse_types((root/f'{family}-{phase}-{stage}.types').read_text().splitlines())
            kinds={n['filterClass'] for n in native['nodes'] if n['filter']}
            expected={'vvp_wire_vec4','vvp_wire_vec8'}
            if phase=='early' or stage:expected.add(classes[family])
            if kinds!=expected:raise ValueError('Missing unsupported/admitted native class evidence')
            if native['tick']!={0:0,1:1000,3:1000,2:2000,4:2000}[stage]:raise ValueError('Wrong native class time')
        for mode in ('baseline','disabled','observe'):
            name=f'{family}-{phase}-{mode}';lines=(root/(name+'.stdout')).read_text().splitlines()
            if receipt['runs'][name]['exitCode'] or (root/(name+'.stderr')).read_text():raise ValueError('Failed family continuation')
            expected=[f'RAW_FAMILY {family} {phase}']
            if mode=='observe':
                if phase=='early':expected.append('RAW_REFUSED 0');refusals+=1
                else:
                    if len(lines)<6 or lines[1]!='RAW_ADMITTED 0':raise ValueError('Missing initial admitted inventory')
                    raw=parse_raw(lines[2:5])
                    if raw['tick'] or len(raw['filters'])!=1 or raw['filters'][0]['vectors']!=[bytes(1),b'']:raise ValueError('Wrong initial raw cache')
                    types=parse_types((root/f'{family}-{phase}-0.types').read_text().splitlines())
                    node=next(n for n in types['nodes'] if n['filterClass']=='vvp_wire_vec8');wire=raw['filters'][0]
                    if (node['id'],node['key'],node['filter'])!=(wire['id'],wire['node'],wire['pointer']):raise ValueError('Initial raw filter rebound')
                    expected+=lines[1:5]
            for step in (1,2):
                if mode=='observe':expected.append(f'RAW_REFUSED {step}');refusals+=1
                expected.append(f'RAW_VALUE {step} admitted {step-1}')
                expected.append(f'RAW_REAL {step} '+('1.25' if step==1 else '-2.50') if family=='real' else f'RAW_VALUE {step} foreign {2-step}')
                if mode=='observe':expected.append(f'RAW_REFUSED {step+2}');refusals+=1
            if len(lines)!=len(expected)+1 or lines[:-1]!=expected or '$finish called at 3000 (1ps)' not in lines[-1]:raise ValueError('Changed continuation or partial inventory emitted')
    return dict(qualified=False,controlsPassed=True,unsupportedProfilesRefused=list(FAMILIES),allocationPhases=['early','late'],
        noPartialInventory=True,refusedObservations=refusals,originalDisabledAndRefusedContinuationExactlyEqual=True,
        scope='Exact raw-wire class admission rejects native real filters and vec4/vec8 subclasses with private behavior before output, both at startup and after an admitted inventory. Native continuation after repeated refusals matches original and disabled controls.',
        notEstablished=['Support for rejected classes or every plugin-defined subclass','Compact encoding and operational board integration','General rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/wire_raw_family.'+ext),out/('probe.'+ext))
    commands=[]
    for family,phase in CASES:
        family=family+'-'+phase
        command=['iverilog','-g2012','-o',str(out/(family+'.vvp')),str(out/'probe.v')]
        commands.append(command);subprocess.run(command,check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    command=['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')];commands.append(command);subprocess.run(command,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for family,phase in CASES:
        for mode in ('baseline','disabled','observe'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,K7658_RAW_FAMILY=family,K7658_RAW_PHASE=phase,K7658_RAW_MODE='off' if mode in ('baseline','disabled') else mode)
            env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',family+'-'+phase+'.vvp']
            r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30);name=family+'-'+phase+'-'+mode
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
            runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Runtime changed during probe')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('wire_raw_family_probe.py','wire_raw_probe.py','wire_probe.py','strength_encoding_probe.py','net_types_probe.py','net_probe.py','fixtures/wire_raw_family.cc','fixtures/wire_raw_family.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('candidate','baseline','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Unsupported raw-wire filter families refused without partial inventory.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
