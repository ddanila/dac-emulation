#!/usr/bin/env python3
"""Check compact island admission before and after reference initialization."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
from island_raw_family import CASES,review as dense_review
from island_raw_delta import block,image,reconstruct
HERE=Path(__file__).resolve().parent

def review(root):
    refusals=0;admissions=0
    with tempfile.TemporaryDirectory() as directory:
        copied=Path(directory)
        shutil.copy2(root/'run.json',copied/'run.json')
        for family,phase in CASES:
            for mode in ('baseline','disabled','observe'):
                name=f'{family}-{phase}-{mode}';lines=(root/(name+'.stdout')).read_text().splitlines();out=[];markers=[];frames=[];i=0
                while i<len(lines):
                    if lines[i].startswith('IX_REFUSED '):markers.append(lines[i]);refusals+=1;i+=1
                    elif lines[i].startswith('VIX_BEGIN '):
                        frame,i=block(lines,i);frames.append(frame)
                    else:out.append(lines[i]);i+=1
                expected=[]
                if mode=='observe':
                    expected=['IX_REFUSED NOREF 0']
                    if phase=='early':expected.extend(f'IX_REFUSED {kind} {stage}' for stage in (0,1,3,2,4) for kind in ('R','D'))
                    else:expected+=['IX_REFUSED DUPLICATE 0']+[f'IX_REFUSED D {stage}' for stage in (1,3,2,4)]
                if markers!=expected:raise ValueError('Missing compact admission/lifecycle refusal')
                if mode=='observe' and phase=='late':
                    if len(frames)!=2 or frames[0]['mode']!='R':raise ValueError('Missing initial compact admission')
                    start=next(i for i,l in enumerate(out) if l.startswith('VIR_BEGIN '));end=next(i for i in range(start,len(out)) if out[i].startswith('VIR_END '))+1
                    if image(frames[0]['tick'],frames[0]['rows'])!=out[start:end] or reconstruct(frames[0]['rows'],frames[1])!=out[start:end]:raise ValueError('Incorrect compact initial population')
                    admissions+=1
                elif frames:raise ValueError('Partial unsupported compact output')
                (copied/(name+'.stdout')).write_text('\n'.join(out)+'\n');shutil.copy2(root/(name+'.stderr'),copied/(name+'.stderr'))
        result=dense_review(copied)
    result.update(compactRefusals=refusals,initialCompactAdmissions=admissions,scope='Native island, branch and port subclasses reject compact references/differences before any output, both initially and after valid reference admission. Deltas before reference and duplicate reference initialization also refuse. Full native private subclass behavior and original continuation are preserved.',notEstablished=['Every plugin family, freed storage and operational board integration'])
    return result

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/island_raw_delta_family.cc' if ext=='cc' else 'fixtures/island_raw_family.v'),out/('probe.'+ext))
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
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('island_raw_delta_family.py','island_raw_delta.py','island_raw_family.py','island_raw_probe.py','island_probe.py','wire_raw_probe.py','net_probe.py','fixtures/island_raw_delta_family.cc','fixtures/island_raw_family.v')}),indent=2)+'\n')
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
