#!/usr/bin/env python3
"""Qualify early/late island family refusal without partial output or changed continuation."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_types_probe import parse as parse_types

HERE=Path(__file__).resolve().parent
FAMILIES=('island','branch','port')
CASES=tuple((f,p) for f in FAMILIES for p in ('early','late'))

def review(root):
    from island_raw_probe import parse
    receipt=json.loads((root/'run.json').read_text());refusals=0
    for family,phase in CASES:
        ordinary_reference=None
        for mode in ('baseline','disabled','observe'):
            name=f'{family}-{phase}-{mode}';lines=(root/(name+'.stdout')).read_text().splitlines()
            if receipt['runs'][name]['exitCode'] or (root/(name+'.stderr')).read_text():raise ValueError('Failed family continuation')
            stages=[];ordinary=[];i=0;types=[]
            while i<len(lines):
                line=lines[i]
                if line.startswith('RAW_REFUSED '):stages.append(int(line.split()[1]));refusals+=1;i+=1
                elif line=='RAW_ADMITTED 0':
                    start=i+1;i=start
                    while i<len(lines) and not lines[i].startswith('VIR_END '):i+=1
                    if i==len(lines):raise ValueError('Truncated admission')
                    state=parse(lines[start:i+1]);i+=1
                    if phase!='late' or stages or state['tick'] or len(state['islands'])!=1 or len(state['islands'][0]['ports'])!=2 or any(v for p in state['islands'][0]['ports'] for v in p['vectors'].values()):raise ValueError('Wrong prior admitted state')
                    stages.append('admitted')
                elif line.startswith('RAW_TYPES '):types.append(line);i+=1
                else:ordinary.append(line);i+=1
            expected=[0,1,3,2,4] if phase=='early' else ['admitted',1,3,2,4]
            if stages!=(expected if mode=='observe' else []):raise ValueError('Missing initial/late raw refusal')
            classnames={'island':['11ExtraIsland','22vvp_island_branch_tran','15vvp_island_port'],'branch':['15vvp_island_tran','11ExtraBranch','15vvp_island_port'],'port':['15vvp_island_tran','22vvp_island_branch_tran','9ExtraPort']}[family]
            want=[f'RAW_TYPES {stage} '+ ' '.join(classnames) for stage in expected if isinstance(stage,int)] if mode=='observe' else []
            if types!=want:raise ValueError('Missing native family evidence')
            if not ordinary or ordinary[0]!=f'RAW_FAMILY {family} {phase}' or '$finish called at 3000 (1ps)' not in ordinary[-1]:raise ValueError('Incomplete family fixture')
            values=[l for l in ordinary if l.startswith('VALUE ')]
            want=[]
            for step in (1,2):want.extend([f'VALUE {step*1000} admitted {step-1}',f'VALUE {step*1000} foreign {step-1 if family=="island" else 2-step}'])
            if values!=want:raise ValueError('Changed native fixture values')
            if [l for l in ordinary if l.startswith('PRIVATE_RUN ')]!=(['PRIVATE_RUN 1','PRIVATE_RUN 2'] if family=='island' else []):raise ValueError('Missing private subclass behavior')
            if ordinary_reference is None:ordinary_reference=ordinary
            elif ordinary!=ordinary_reference:raise ValueError('Changed continuation or partial inventory')
    return dict(qualified=False,controlsPassed=True,unsupportedFamilies=list(FAMILIES),refusedObservations=refusals,noPartialInventory=True,originalContinuationExactlyEqual=True,scope='Native raw island observation rejects island, branch and port subclasses before partial output, both at startup and after valid admission. Private subclass behavior and original-runtime continuation remain intact.',notEstablished=['Supported allocation growth and direct input coverage','Every plugin family, compact/board integration or general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/island_raw_family.'+ext),out/('probe.'+ext))
    source=(candidate/'vvp/island_tran.cc').read_text()
    a=source.index('class vvp_island_tran :');b=source.index('vvp_island_branch_tran::vvp_island_branch_tran(',a)
    (out/'island_fixture.h').write_text('#include "vvp_island.h"\n'+source[a:b])
    commands=[]
    for family,phase in CASES:
        family=family+'-'+phase
        command=['iverilog','-g2012','-o',str(out/(family+'.vvp')),str(out/'probe.v')]
        commands.append(command);subprocess.run(command,check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    command=['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')];commands.append(command);subprocess.run(command,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'island_fixture.h',*modules.glob('*.vpi')]};runs={}
    for family,phase in CASES:
        for mode in ('baseline','disabled','observe'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,K7658_ISLAND_FAMILY=family,K7658_ISLAND_PHASE=phase,K7658_ISLAND_MODE='off' if mode in ('baseline','disabled') else mode)
            env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',family+'-'+phase+'.vvp']
            r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30);name=family+'-'+phase+'-'+mode
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
            runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Runtime changed during probe')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('island_raw_family.py','island_raw_probe.py','island_probe.py','wire_raw_probe.py','net_probe.py','fixtures/island_raw_family.cc','fixtures/island_raw_family.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('candidate','baseline','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Unsupported raw island families refused without partial inventory.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
