#!/usr/bin/env python3
"""Qualify early/late concat subclass refusal without partial output or changed continuation."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_types_probe import parse as parse_types
from concat_probe import parse as parse_concat
HERE=Path(__file__).resolve().parent
FAMILIES=('derived4','derived8')
CASES=tuple((f,p) for f in FAMILIES for p in ('early','late'))

def review(root):
    receipt=json.loads((root/'run.json').read_text());refusals=0
    for family,phase in CASES:
        for stage in (0,1,3,2,4):
            native=parse_types((root/f'{family}-{phase}-{stage}.types').read_text().splitlines())
            kinds={n['funClass'] for n in native['nodes'] if n['fun']}
            expected={'vvp_fun_concat8','Sink'}
            if phase=='early' or stage:expected.add('ExtraConcat4' if family=='derived4' else 'ExtraConcat8')
            if kinds!=expected:raise ValueError('Missing native class evidence')
            if native['tick']!={0:0,1:1000,3:1000,2:2000,4:2000}[stage]:raise ValueError('Wrong class observation time')
        for mode in ('baseline','disabled','observe'):
            name=f'{family}-{phase}-{mode}';lines=(root/(name+'.stdout')).read_text().splitlines()
            if receipt['runs'][name]['exitCode'] or (root/(name+'.stderr')).read_text():raise ValueError('Failed family continuation')
            expected=[f'CONCAT_FAMILY {family} {phase}']
            if mode=='observe':
                if phase=='early':expected.append('CONCAT_REFUSED 0');refusals+=1
                else:
                    if len(lines)<6 or lines[1]!='CONCAT_ADMITTED 0':raise ValueError('Missing prior admitted inventory')
                    frame=parse_concat(lines[2:5])
                    if frame['tick'] or frame['events'] or len(frame['nodes'])!=1:raise ValueError('Wrong initial inventory')
                    c=frame['nodes'][0]
                    if c['kind']!=8 or c['widths']!=[1,0,0,0] or c['width']!=1 or c['bits']!='00' or c['pending']:raise ValueError('Wrong admitted constructor')
                    native=parse_types((root/f'{family}-{phase}-0.types').read_text().splitlines())
                    n=next(n for n in native['nodes'] if n['funClass']=='vvp_fun_concat8')
                    if (n['id'],n['key'],n['fun'])!=(c['id'],c['node'],c['fun']):raise ValueError('Rebound initial concat')
                    expected+=lines[1:5]
            for step in (1,2):
                if mode=='observe':expected.extend([f'CONCAT_REFUSED {step}',f'CONCAT_REFUSED {step+2}']);refusals+=2
                expected.extend([f'CONCAT_VALUE {step*1000} admitted {step-1}',f'CONCAT_VALUE {step*1000} foreign {2-step}'])
            if len(lines)!=len(expected)+1 or lines[:-1]!=expected or '$finish called at 3000 (1ps)' not in lines[-1]:raise ValueError('Changed continuation or partial inventory')
    return dict(qualified=False,controlsPassed=True,unsupportedProfilesRefused=list(FAMILIES),allocationPhases=['early','late'],refusedObservations=refusals,noPartialInventory=True,originalDisabledAndRefusedContinuationExactlyEqual=True,scope='Exact concat4/concat8 admission rejects subclasses with additional private stimulus state before output, at startup and after a valid inventory. Continued native propagation agrees with original and disabled controls.',notEstablished=['Support for rejected subclasses','Admitted allocation growth, board binding and integration','General rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/concat_family.'+ext),out/('probe.'+ext))
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
            env=dict(os.environ,K7658_CONCAT_FAMILY=family,K7658_CONCAT_PHASE=phase,K7658_CONCAT_MODE='off' if mode in ('baseline','disabled') else mode)
            env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',family+'-'+phase+'.vvp']
            r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30);name=family+'-'+phase+'-'+mode
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
            runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Runtime changed during probe')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('concat_family_probe.py','concat_probe.py','net_types_probe.py','net_probe.py','fixtures/concat_family.cc','fixtures/concat_family.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('candidate','baseline','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Unsupported concatenation families refused without partial inventory.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
