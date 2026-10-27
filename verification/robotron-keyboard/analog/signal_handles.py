#!/usr/bin/env python3
"""Replay native initialized signal metadata and existing bit-handle cache controls."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from net_probe import pointer
from ttl7406_probe import sha
from callback_referents import EXPECTED
HERE=Path(__file__).resolve().parent
REFUSALS=['node','scope','name','array-arm','cache','bit-base','bit-index','bit-parent']


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VSH_BEGIN','1']:raise ValueError('Invalid signal handle header')
    tick=int(a[2]);rows=[];i=1
    while i<len(lines) and lines[i].startswith('VSH_SIGNAL '):
        a=lines[i].split();i+=1
        if len(a)!=15:raise ValueError('Invalid signal metadata')
        row=dict(id=int(a[1]),pointer=pointer(a[2]),kind=a[3],node=pointer(a[4]),nodeId=int(a[5]),scope=pointer(a[6]),scopeId=int(a[7]),signed=int(a[8]),msb=int(a[9]),lsb=int(a[10]),namePointer=pointer(a[11]),nameLength=int(a[12]),bits=pointer(a[13]),count=int(a[14]))
        if min(row[k] for k in ('id','pointer','node','nodeId','scope','scopeId'))<=0 or row['signed'] not in (0,1) or row['count']<0 or row['nameLength']<0:raise ValueError('Invalid initialized signal identity')
        if row['kind'] not in ('10signal_reg','10signal_net','14signal_integer'):raise ValueError('Unsupported signal class')
        a=lines[i].split();i+=1
        if len(a)!=2 or a[0]!='VSH_NAME':raise ValueError('Missing signal name')
        if not row['namePointer']:
            if a[1]!='-' or row['nameLength']:raise ValueError('Invalid null name')
            row['name']=None
        else:
            data=bytes.fromhex(a[1])
            if len(data)!=row['nameLength']+1:raise ValueError('Invalid name allocation')
            row['name']=data.hex()
        row['cache']=[]
        if bool(row['bits'])!=bool(row['count']):raise ValueError('Invalid bit allocation')
        for n in range(row['count']):
            a=lines[i].split();i+=1
            if len(a)!=6 or a[0]!='VSH_BIT' or int(a[1])!=n:raise ValueError('Invalid bit ordering')
            bit=dict(pointer=pointer(a[2]),base=pointer(a[3]),index=pointer(a[4]),value=int(a[5]))
            if bit['base']!=row['bits'] or min(bit[k] for k in ('pointer','index'))<=0:raise ValueError('Invalid bit binding')
            row['cache'].append(bit)
        if len({b['index'] for b in row['cache']})!=row['count'] or len({b['pointer'] for b in row['cache']})!=row['count']:raise ValueError('Aliased bit allocation')
        rows.append(row)
    if i!=len(lines)-1 or lines[i]!=f'VSH_END {len(rows)}':raise ValueError('Invalid signal footer')
    ids=[r['id'] for r in rows]
    if ids!=sorted(set(ids)) or len({r['pointer'] for r in rows})!=len(rows):raise ValueError('Aliased signal handles')
    return dict(tick=tick,rows=rows)


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native signal control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];refusals=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and not lines[i].startswith('VSH_END '):i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid signal image')
                i+=1;images[key]=parse(lines[start:i]);continue
            if line.startswith('REFUSED '):refusals.append(line.split()[1]);continue
            events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=EXPECTED or refusals!=(REFUSALS if mode=='enabled' else []):raise ValueError('Changed native signal continuation/refusals')
    if set(images)!={'before','node','signed','range','restored','bit-cache','index-value','cached-restored'}:raise ValueError('Missing signal controls')
    before=images['before']
    if before['tick']!=1000 or len(before['rows'])!=2:raise ValueError('Invalid initialized signal population')
    index=next((i for i,r in enumerate(before['rows']) if r['signed']==1),None)
    if index is None:raise ValueError('Missing signed signal')
    a=before['rows'][index];b=before['rows'][1-index]
    if a['msb']!=3 or a['lsb']!=0 or a['cache'] or b['cache']:raise ValueError('Invalid initial metadata')
    for label,updates in [('node',{'node':b['node'],'nodeId':b['nodeId']}),('signed',{'signed':0}),('range',{'msb':0,'lsb':3}),('restored',{})]:
        expected=copy.deepcopy(before);expected['rows'][index].update(updates)
        if images[label]!=expected:raise ValueError('Uncovered signal metadata: '+label)
    cached=images['bit-cache'];row=cached['rows'][index]
    if row['count']!=4 or not row['bits'] or [r['value'] for r in row['cache']]!=list(range(4)):raise ValueError('Missing bit-cache allocation')
    expected=copy.deepcopy(before)
    for k in ('bits','count','cache'):expected['rows'][index][k]=row[k]
    if cached!=expected or images['cached-restored']!=cached:raise ValueError('Bit-cache mutation did not restore')
    expected=copy.deepcopy(cached);expected['rows'][index]['cache'][0]['value']=7
    if images['index-value']!=expected:raise ValueError('Missing bit-index value mutation')
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,scope='Explicitly admitted initialized native signal handles: node/scope allocation identities, name storage, signedness, ranges and existing lazy bit caches. Native metadata mutations are visible; foreign pointers and net-array union arms refuse without output and restore before continuation. Observation does not create bit handles. This fixture covers reg handles; net/integer class controls, lifecycle, board bindings and operational integration remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/signal_handles.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
