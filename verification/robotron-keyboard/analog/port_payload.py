#!/usr/bin/env python3
"""Replay guarded native port payload changes and zero-output refusals."""
import argparse,json,os,platform,shutil,subprocess,copy
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
HERE=Path(__file__).resolve().parent


def parse(lines):
    if not lines:raise ValueError('Empty port payload')
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VPP_BEGIN','1'] or int(a[2])<0:raise ValueError('Invalid port payload header')
    tick=int(a[2]);ports=[];i=1;ids=set();pointers=set();bit_count=0
    def identity(ident,address):
        if ident<=0 or address<=0 or ident in ids or address in pointers:raise ValueError('Aliased port payload identity')
        ids.add(ident);pointers.add(address)
    while i<len(lines) and lines[i].startswith('VPP_PORT '):
        a=lines[i].split();i+=1
        if len(a)!=10:raise ValueError('Invalid port row')
        row=dict(id=int(a[1]),pointer=pointer(a[2]),scope=int(a[3]),index=int(a[4]),direction=int(a[5]),width=int(a[6]),node=pointer(a[7]),nodeId=int(a[8]),nameBytes=int(a[9]))
        identity(row['id'],row['pointer'])
        if row['scope']<=0 or row['index']<0 or row['width']<0 or row['nameBytes']<=0 or bool(row['node'])!=bool(row['nodeId']) or row['nodeId']<0:raise ValueError('Invalid port fields')
        if i>=len(lines):raise ValueError('Missing port name')
        a=lines[i].split();i+=1
        if len(a)!=2 or a[0]!='VPP_NAME' or len(a[1])!=2*row['nameBytes'] or bytes.fromhex(a[1]).hex()!=a[1]:raise ValueError('Invalid bounded port name')
        row['name']=a[1];row['bits']=[]
        if row['width']>len(lines)-i:raise ValueError('Truncated port bits')
        for _ in range(row['width']):
            a=lines[i].split();i+=1
            if len(a)!=4 or a[0]!='VPP_BIT':raise ValueError('Missing port bit')
            bit=dict(id=int(a[1]),pointer=pointer(a[2]),index=int(a[3]));identity(bit['id'],bit['pointer'])
            if bit['index']<0:raise ValueError('Invalid port bit index')
            row['bits'].append(bit);bit_count+=1
        ports.append(row)
    if lines[i:]!=[f'VPP_END {len(ports)} {bit_count}'] or [p['id'] for p in ports]!=sorted(p['id'] for p in ports):raise ValueError('Incomplete/unsorted port payload')
    return dict(tick=tick,ports=ports)


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={};expected=[]
    for i in (1,2):expected += [f'ROUND {i}','ORDER before 0 1 2 3','ORDER swapped 1 0 2 3',*['REFUSED '+s for s in ('foreign','duplicate','missing','overflow')],f'RESTORED {i}']
    expected += ['CONTINUE 5 5','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native port payload control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid port payload image')
                images[key]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Changed port continuation/refusal')
    if set(images)!={f'{kind}{i}' for i in (1,2) for kind in ('before','swapped','renamed','restored')}:raise ValueError('Missing port controls')
    for i in (1,2):
        before=images[f'before{i}']
        if before!=images[f'restored{i}'] or before['tick']!=i*1000 or len(before['ports'])!=2:raise ValueError('Port restoration or population differs')
        expected=copy.deepcopy(before);row=expected['ports'][0];row['bits'][0],row['bits'][1]=row['bits'][1],row['bits'][0]
        if expected!=images[f'swapped{i}']:raise ValueError('Wrong port order change')
        expected=copy.deepcopy(before);expected['ports'][0]['name']='58'+expected['ports'][0]['name'][2:]
        if expected!=images[f'renamed{i}']:raise ValueError('Wrong port name change')
    return dict(qualified=False,controlsPassed=True,rounds=2,originalContinuationExactlyEqual=True,
        resolvedNonNullPortReferences=sum(bool(p['node']) for p in images['before1']['ports']),
        scope='Native port fields, bounded names and ordered bit identities distinguish restored bit-order/name mutations. Four invalid bit vectors per round refuse with negative status and zero output, before unsafe iteration. Original/disabled/enabled HDL continuation agrees. Deferred reference readiness is tracked at native resolver handoff; exhaustive early-resolution, subclass/lifecycle and operational board qualification remain separate.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/port_payload.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
