#!/usr/bin/env python3
"""Reconstruct complete native graph images from fixed-reference differences."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import net_probe as dense
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def block(lines,start=0):
    a=lines[start].split()
    if len(a)!=5 or a[0]!='VND_BEGIN' or a[1] not in ('R','D'):raise ValueError('Invalid graph delta header')
    mode=a[1];tick,total,count=map(int,a[2:]);rows={};i=start+1
    if tick<0 or total<=0 or count<0 or count>total:raise ValueError('Invalid graph delta dimensions')
    for _ in range(count):
        if i>=len(lines):raise ValueError('Missing graph delta rows')
        row=lines[i].split();i+=1
        if len(row)!=11 or row[0]!='VNG_NODE':raise ValueError('Invalid delta node')
        identity=int(row[1])
        if not 0<identity<=total or identity in rows or (rows and identity<=max(rows)):raise ValueError('Duplicate/unordered delta identity')
        dense.parse([f'VNG_BEGIN 1 {tick} 1',' '.join([row[0],'1',*row[2:]]),'VNG_END 1'])
        rows[identity]=lines[i-1]
    if i>=len(lines) or lines[i]!=f'VND_END {count}':raise ValueError('Invalid delta footer')
    if mode=='R' and set(rows)!=set(range(1,total+1)):raise ValueError('Incomplete graph reference')
    return dict(mode=mode,tick=tick,total=total,rows=rows),i+1


def reconstruct(reference,frame):
    if frame['mode']!='D' or frame['total']<len(reference):raise ValueError('Wrong graph delta/lifecycle')
    rows=dict(reference)
    for identity,row in frame['rows'].items():
        if reference.get(identity)==row:raise ValueError('Redundant graph delta row')
        rows[identity]=row
    if set(rows)!=set(range(1,frame['total']+1)):raise ValueError('Missing new graph allocation')
    result=[f"VNG_BEGIN 1 {frame['tick']} {frame['total']}",*[rows[i] for i in sorted(rows)],f"VNG_END {frame['total']}"]
    dense.parse(result)
    return result


def separate(lines):
    output=[];frames=[];reference=None;reference_bytes=0;i=0
    while i<len(lines):
        if lines[i].startswith('VND_BEGIN '):
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
        if output[i].startswith('VNG_BEGIN '):
            start=i
            while i<len(output) and not output[i].startswith('VNG_END '):i+=1
            if i==len(output):raise ValueError('Incomplete dense graph')
            full.append(output[start:i+1])
        i+=1
    if len(full)!=len(frames):raise ValueError('Missing full/delta pair')
    for a,(b,_) in zip(full,frames):
        if a!=b:raise ValueError('Delta reconstruction changed graph image')
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
    if not count or not 0<delta_bytes+reference_bytes<full_bytes:raise ValueError('No lossless graph savings')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/net_delta_probe.c' if ext=='c' else 'fixtures/net_probe.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_NET_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('net_delta_probe.py','net_probe.py','fixtures/net_delta_probe.c','fixtures/net_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed graph assessment')
        print('Exact graph delta reconstruction and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
