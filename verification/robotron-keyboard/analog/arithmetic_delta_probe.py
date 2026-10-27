#!/usr/bin/env python3
"""Reconstruct complete native arithmetic images from fixed-reference differences."""
import argparse,re,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import arithmetic_probe as dense
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def image(tick,rows):
    lines=[f'VAR_BEGIN 1 {tick}']
    for identity,row in sorted(rows.items()):
        part=row.splitlines()
        if not row.endswith('\n') or not part or not part[0].startswith(f'VAR_NODE {identity} '):raise ValueError('Wrong arithmetic record identity')
        single=dense.parse([f'VAR_BEGIN 1 {tick}',*part,'VAR_END 1'])
        if single['nodes'][0]['id']!=identity:raise ValueError('Wrong arithmetic identity')
        lines.extend(part)
    lines.append(f'VAR_END {len(rows)}');dense.parse(lines)
    return lines


def block(lines,start=0):
    a=lines[start].split()
    if len(a)!=5 or a[0]!='VAD_BEGIN' or a[1] not in ('R','D'):raise ValueError('Invalid arithmetic delta header')
    mode=a[1];tick,total,count=map(int,a[2:]);rows={};i=start+1
    if tick<0 or total<=0 or count<0 or count>total:raise ValueError('Invalid arithmetic delta dimensions')
    for _ in range(count):
        if i>=len(lines):raise ValueError('Missing arithmetic delta rows')
        row=lines[i].split();i+=1
        if len(row)!=5 or row[0]!='VAD_ROW':raise ValueError('Invalid arithmetic delta row')
        identity,prefix,suffix=map(int,row[1:4])
        if identity<=0 or min(prefix,suffix)<0 or identity in rows or (rows and identity<=max(rows)):raise ValueError('Invalid delta identity/range')
        if row[4]!='-' and not re.fullmatch(r'(?:[0-9a-f]{2})+',row[4]):raise ValueError('Invalid delta bytes')
        data='' if row[4]=='-' else bytes.fromhex(row[4]).decode('ascii')
        if mode=='R':
            if prefix or suffix:raise ValueError('Reference depends on previous state')
            rows[identity]=data
        else:rows[identity]=(prefix,suffix,data)
    if i>=len(lines) or lines[i]!=f'VAD_END {count}':raise ValueError('Invalid delta footer')
    if mode=='R':
        if len(rows)!=total:raise ValueError('Incomplete arithmetic reference')
        image(tick,rows)
    return dict(mode=mode,tick=tick,total=total,rows=rows),i+1


def reconstruct(reference,frame):
    if frame['mode']!='D' or frame['total']<len(reference):raise ValueError('Wrong arithmetic delta mode/lifecycle')
    rows=dict(reference)
    for identity,(prefix,suffix,data) in frame['rows'].items():
        old=reference.get(identity,'')
        if prefix+suffix>len(old):raise ValueError('Signal splice exceeds reference')
        row=old[:prefix]+data+(old[len(old)-suffix:] if suffix else '')
        if row==old:raise ValueError('Redundant arithmetic delta row')
        rows[identity]=row
    if len(rows)!=frame['total']:raise ValueError('Missing new arithmetic rows')
    return image(frame['tick'],rows)


def separate(lines):
    output=[];frames=[];reference=None;reference_bytes=0;i=0
    while i<len(lines):
        if lines[i].startswith('VAD_BEGIN '):
            frame,end=block(lines,i);size=len(('\n'.join(lines[i:end])+'\n').encode());i=end
            if frame['mode']=='R':
                if reference is not None or frames:raise ValueError('Graph reference reset')
                reference=frame['rows'];reference_bytes=size
            else:
                if reference is None:raise ValueError('Graph delta before reference')
                frames.append((reconstruct(reference,frame),size))
        else:output.append(lines[i]);i+=1
    full=[];i=0
    while i<len(output):
        if output[i].startswith('VAR_BEGIN '):
            start=i
            while i<len(output) and not output[i].startswith('VAR_END '):i+=1
            if i==len(output):raise ValueError('Incomplete dense arithmetic')
            full.append(output[start:i+1])
        i+=1
    if len(full)!=len(frames):raise ValueError('Missing full/delta pair')
    for a,(b,_) in zip(full,frames):
        if a!=b:raise ValueError('Delta reconstruction changed arithmetic image')
    return output,len(full),sum(len(('\n'.join(f)+'\n').encode()) for f in full),sum(size for _,size in frames),reference_bytes


def review(root):
    count=full_bytes=delta_bytes=reference_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for p in copied.glob('*.stdout'):
            lines,n,full,delta,reference=separate(p.read_text().splitlines())
            p.write_text('\n'.join(lines)+'\n' if lines else '')
            count+=n;full_bytes+=full;delta_bytes+=delta;reference_bytes+=reference
        result=dense.review(copied)
    if not count or min(delta_bytes,reference_bytes,full_bytes)<=0:raise ValueError('Missing arithmetic delta evidence')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/arithmetic_delta_probe.cc' if ext=='cc' else 'fixtures/arithmetic_probe.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate/'vvp'),'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_ARITHMETIC_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('arithmetic_delta_probe.py','arithmetic_probe.py','net_probe.py','fixtures/arithmetic_delta_probe.cc','fixtures/arithmetic_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed arithmetic assessment')
        print('Exact arithmetic delta reconstruction and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
