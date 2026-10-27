#!/usr/bin/env python3
"""Verify lossless initialized-flag encoding against dense native snapshots."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import thread_probe as base
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
DENSE_PARSER=base.parse_snapshot


def expand(lines):
    result=[]
    for line in lines:
        if not line.startswith('VT_FLAGS_SPARSE '):result.append(line);continue
        a=line.split()
        if len(a)<3 or a[1]!='512' or int(a[2])!=len(a)-3:raise ValueError('Invalid sparse flag header')
        flags=['-']*512;previous=-1
        for item in a[3:]:
            pair=item.split(':')
            if len(pair)!=2:raise ValueError('Invalid sparse flag item')
            index=int(pair[0]);value=pair[1]
            if not previous<index<512 or value not in ('0','1','2','3'):raise ValueError('Unordered/aliased sparse flags')
            flags[index]=value;previous=index
        result.append('VT_FLAGS 512 '+''.join(flags))
    return result


def parse_snapshot(lines):return DENSE_PARSER(expand(lines))


def review(root):
    pairs=compact_bytes=dense_bytes=0
    with tempfile.TemporaryDirectory() as directory:
        temporary=Path(directory)
        for mode in ('baseline','disabled','enabled','corrupt'):
            lines=(root/(mode+'.stdout')).read_text().splitlines();clean=[];i=0;before=None;count=0;boundaries=0
            while i<len(lines):
                line=lines[i]
                if line=='VTM_BEFORE':
                    start=i+1;end=next((j for j in range(start,len(lines)) if lines[j].startswith('VT_END ')),None)
                    if end is None:raise ValueError('Truncated compact before state')
                    before=lines[start:end+1];boundaries+=1
                if line=='VTM_DENSE':
                    start=i+1;end=next((j for j in range(start,len(lines)) if lines[j].startswith('VT_END ')),None)
                    if before is None or end is None:raise ValueError('Orphan dense state')
                    dense=lines[start:end+1]
                    if parse_snapshot(before)!=DENSE_PARSER(dense):raise ValueError('Sparse encoding changed native state')
                    compact_bytes+=sum(len(l)+1 for l in before);dense_bytes+=sum(len(l)+1 for l in dense)
                    count+=1;pairs+=1;before=None;i=end+1;continue
                clean.append(line);i+=1
            if count!=boundaries or bool(count)!=(mode in ('enabled','corrupt')):raise ValueError('Missing dense equivalence controls')
            (temporary/(mode+'.stdout')).write_text('\n'.join(clean)+'\n')
            shutil.copyfile(root/(mode+'.stderr'),temporary/(mode+'.stderr'))
        try:
            base.parse_snapshot=parse_snapshot
            result=base.review(temporary)
        finally:base.parse_snapshot=DENSE_PARSER
    if compact_bytes>=dense_bytes:raise ValueError('No logical log reduction')
    result.update(denseAndCompactSnapshotsExactlyEqual=True,matchedSnapshots=pairs,compactSnapshotBytes=compact_bytes,denseSnapshotBytes=dense_bytes)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/thread_compact_probe.c' if ext=='c' else 'fixtures/thread_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_THREAD_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('thread_compact_probe.py','thread_probe.py','fixtures/thread_compact_probe.c','fixtures/thread_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Compact thread snapshots match dense native state and restored controls.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
