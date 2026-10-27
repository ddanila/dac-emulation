#!/usr/bin/env python3
"""Qualify early/late concat subclass refusal without partial output or changed continuation."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
from net_types_probe import parse as parse_types
from concat_probe import parse as parse_concat
HERE=Path(__file__).resolve().parent
FAMILIES=('derived4','derived8')
CASES=tuple((f,p) for f in FAMILIES for p in ('early','late'))

def review(root):
    import concat_family_probe as dense
    from concat_delta_probe import block,reconstruct,image
    count=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for family,phase in CASES:
            path=copied/f'{family}-{phase}-observe.stdout';lines=path.read_text().splitlines();output=[];ref=None;stages=[];i=0
            while i<len(lines):
                if lines[i]=='CCD_REFERENCE':
                    if phase!='late' or ref is not None:raise ValueError('Unexpected compact admission reference')
                    ref,end=block(lines,i+1)
                    if ref['mode']!='R':raise ValueError('Missing compact reference')
                    begin=next(j for j,l in enumerate(output) if l.startswith('VCN_BEGIN '))
                    if image(ref['tick'],ref['rows'],ref['events'])!=output[begin:]:raise ValueError('Reference differs from native cache')
                    i=end
                elif lines[i]=='CCD_DELTA':
                    if ref is None:raise ValueError('Compact observation before reference')
                    frame,end=block(lines,i+1)
                    if frame['rows'] or frame['events'] or reconstruct(ref['rows'],frame)!=image(ref['tick'],ref['rows'],ref['events']):raise ValueError('Initial compact cache differs')
                    stages.append('admitted');i=end
                elif lines[i].startswith('CCD_REFUSED '):
                    stages.append(int(lines[i].split()[1]));i+=1;count+=1
                else:output.append(lines[i]);i+=1
            expected=[0,1,3,2,4] if phase=='early' else ['admitted',1,3,2,4]
            if stages!=expected:raise ValueError('Missing compact family refusals')
            path.write_text('\n'.join(output)+'\n')
        result=dense.review(copied)
    result.update(compactRefusals=count,lateUnsupportedAllocationRefusedAfterValidReference=True,
                  scope='Concat reference admission rejects unsupported initial functors; after a valid reference, dense and compact scans reject later concat4/concat8 subclasses before output. Original/disabled/refused continuation agrees. Repeated reference refusal after initialization is a lifecycle check, not independent family evidence.')
    result['notEstablished']=['Support for rejected classes or every plugin subclass','Operational board integration and general rollback']
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/concat_delta_family.cc' if ext=='cc' else 'fixtures/concat_family.v'),out/('probe.'+ext))
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
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('concat_delta_family.py','concat_delta_probe.py','concat_family_probe.py','concat_probe.py','net_types_probe.py','net_probe.py','fixtures/concat_delta_family.cc','fixtures/concat_family.v')}),indent=2)+'\n')
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
