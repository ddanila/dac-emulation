#!/usr/bin/env python3
"""Check full-scan island differences against dense native fixtures."""
import argparse,importlib,json,lzma,os,platform,re,shutil,subprocess,tempfile
from pathlib import Path
import island_raw_probe as dense
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
CASES=('growth_callbacks','inputs','strengths','competing','conditional','partselect','feedback')

def image(tick,rows):
    lines=[f'VIR_BEGIN 1 {tick}']
    for identity,row in sorted(rows.items()):
        part=row.splitlines()
        if not row.endswith('\n') or not part or not part[0].startswith(f'VIR_ISLAND {identity} '):raise ValueError('Wrong island record identity')
        single=dense.parse([f'VIR_BEGIN 1 {tick}',*part,'VIR_END 1'])
        if single['islands'][0]['id']!=identity:raise ValueError('Wrong island identity')
        lines.extend(part)
    lines.append(f'VIR_END {len(rows)}');dense.parse(lines)
    return lines


def block(lines,start=0):
    a=lines[start].split()
    if len(a)!=5 or a[0]!='VIX_BEGIN' or a[1] not in ('R','D'):raise ValueError('Invalid island delta header')
    mode=a[1];tick,total,count=map(int,a[2:]);rows={};i=start+1
    if tick<0 or total<0 or count<0 or count>total:raise ValueError('Invalid island delta dimensions')
    for _ in range(count):
        if i>=len(lines):raise ValueError('Missing island delta rows')
        row=lines[i].split();i+=1
        if len(row)!=5 or row[0]!='VIX_ROW':raise ValueError('Invalid island delta row')
        identity,prefix,suffix=map(int,row[1:4])
        if identity<=0 or min(prefix,suffix)<0 or identity in rows or (rows and identity<=max(rows)):raise ValueError('Invalid delta identity/range')
        if row[4]!='-' and not re.fullmatch(r'(?:[0-9a-f]{2})+',row[4]):raise ValueError('Invalid delta bytes')
        data='' if row[4]=='-' else bytes.fromhex(row[4]).decode('ascii')
        if mode=='R':
            if prefix or suffix:raise ValueError('Reference depends on previous state')
            rows[identity]=data
        else:rows[identity]=(prefix,suffix,data)
    if i>=len(lines) or lines[i]!=f'VIX_END {count}':raise ValueError('Invalid delta footer')
    if mode=='R':
        if len(rows)!=total:raise ValueError('Incomplete island reference')
        image(tick,rows)
    return dict(mode=mode,tick=tick,total=total,rows=rows),i+1


def reconstruct(reference,frame):
    if frame['mode']!='D' or frame['total']<len(reference):raise ValueError('Wrong island delta mode/lifecycle')
    rows=dict(reference)
    for identity,(prefix,suffix,data) in frame['rows'].items():
        old=reference.get(identity,'')
        if prefix+suffix>len(old):raise ValueError('Resolver splice exceeds reference')
        row=old[:prefix]+data+(old[len(old)-suffix:] if suffix else '')
        if row==old:raise ValueError('Redundant island delta row')
        rows[identity]=row
    if len(rows)!=frame['total']:raise ValueError('Missing new island rows')
    return image(frame['tick'],rows)


def separate(lines):
    output=[];frames=[];reference=None;reference_bytes=0;i=0
    while i<len(lines):
        if lines[i].startswith('VIX_BEGIN '):
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
        if output[i].startswith('VIR_BEGIN '):
            start=i
            while i<len(output) and not output[i].startswith('VIR_END '):i+=1
            if i==len(output):raise ValueError('Incomplete dense island')
            full.append(output[start:i+1])
        i+=1
    if len(full)!=len(frames):raise ValueError('Missing full/delta pair')
    for a,(b,_) in zip(full,frames):
        if a!=b:raise ValueError('Delta reconstruction changed island image')
    return output,len(full),sum(len(('\n'.join(f)+'\n').encode()) for f in full),sum(size for _,size in frames),reference_bytes


def output_text(root,mode):
    p=root/(mode+'.stdout')
    return p.read_text() if p.exists() else lzma.open(str(p)+'.xz','rt').read()

def review_case(root,case):
    count=full_bytes=delta_bytes=reference_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        shutil.copy2(root/'run.json',copied/'run.json')
        for mode in ('baseline','disabled','enabled','corrupt'):
            lines,n,full,delta,reference=separate(output_text(root,mode).splitlines())
            (copied/(mode+'.stdout')).write_text('\n'.join(lines)+'\n' if lines else '')
            shutil.copy2(root/(mode+'.stderr'),copied/(mode+'.stderr'))
            count+=n;full_bytes+=full;delta_bytes+=delta;reference_bytes+=reference
        result=importlib.import_module('island_raw_'+case).review(copied)
    if not count or min(delta_bytes,reference_bytes,full_bytes)<=0:raise ValueError('Missing compact island evidence')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    return result

def review(root):
    return dict(qualified=False,controlsPassed=True,cases={case:review_case(root/case,case) for case in CASES},scope='Native fixed-reference raw island differences reconstruct complete dense images through allocation growth, live scratch callbacks, full/partial strength inputs, competing drivers, conditional/part-select branches and feedback reevaluation. Every native raw scan and restored fault is preserved. New allocations use full rows.',notEstablished=['Compact unsupported-family refusals and board binding/budgets','Scheduled vector-8 assignment payloads and operational integration','Deleted storage and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    source=(candidate/'vvp/island_tran.cc').read_text()
    header='#include "vvp_island.h"\n'+source[source.index('class vvp_island_tran :'):source.index('vvp_island_branch_tran::vvp_island_branch_tran(')]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    sources={'island_raw_delta.py':sha(Path(__file__))}
    for case in CASES:
        root=out/case;root.mkdir();name='island_raw_'+case
        text=(HERE/('fixtures/'+name+'.cc')).read_text()
        old='int r=api(f);if(fclose(f)||r)exit(2);return p;'
        new='int r=api(f);auto raw=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_inventory");if(api==raw){auto delta=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_delta_inventory");if(!delta || delta(f))exit(2);}if(fclose(f)||r)exit(2);return p;'
        if old not in text:raise ValueError('Changed dense snapshot helper')
        text=text.replace(old,new)
        old='  if(!raw || !legacy)exit(2);'
        new=old+'\n  static bool referenced=false;if(!referenced){auto ref=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_reference");if(!ref || ref(stdout))exit(2);referenced=true;}'
        if old not in text:raise ValueError('Changed dense observer')
        text=text.replace(old,new);(root/'probe.cc').write_text(text);(root/'island_fixture.h').write_text(header)
        shutil.copy2(HERE/('fixtures/'+name+'.v'),root/'probe.v')
        commands=[['iverilog','-g2012','-o',str(root/'probe.vvp'),str(root/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(root/'probe.vpi'),str(root/'probe.cc')]]
        for cmd in commands:subprocess.run(cmd,check=True)
        pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',root/'probe.vpi',root/'island_fixture.h',*modules.glob('*.vpi')]};runs={}
        for mode in ('baseline','disabled','enabled','corrupt'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,K7658_ISLAND_RAW_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,timeout=30)
            (root/(mode+'.stdout')).write_text(r.stdout);(root/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib));r.check_returncode()
        if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Runtime changed during capture')
        for n in (name+'.py','fixtures/'+name+'.cc','fixtures/'+name+'.v'):sources[n]=sha(HERE/n)
        (root/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins),indent=2)+'\n')
        review_case(root,case)
    (out/'run.json').write_text(json.dumps(dict(sources=sources),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Compact raw island images and native continuation verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
