#!/usr/bin/env python3
"""Replay bounded native parameter names, metadata and exact value storage."""
import argparse,json,os,platform,shutil,subprocess,copy,struct
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
HERE=Path(__file__).resolve().parent


def parse(lines):
    if not lines:raise ValueError('Missing parameter image')
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VPM_BEGIN','1'] or int(a[2])<0:raise ValueError('Invalid parameter header')
    tick=int(a[2]);rows=[];i=1
    def hexrow(tag,count):
        nonlocal i
        if i>=len(lines):raise ValueError('Missing parameter bytes')
        a=lines[i].split();i+=1
        if len(a)!=2 or a[0]!=tag or len(a[1])!=2*count or bytes.fromhex(a[1]).hex()!=a[1]:raise ValueError('Invalid parameter byte payload')
        return a[1]
    while i<len(lines) and lines[i].startswith('VPM_PARAM '):
        a=lines[i].split();i+=1
        if len(a)!=9:raise ValueError('Invalid parameter metadata')
        row=dict(id=int(a[1]),pointer=pointer(a[2]),kind=a[3],scope=pointer(a[4]),local=int(a[5]),file=int(a[6]),line=int(a[7]),nameBytes=int(a[8]))
        if min(row[k] for k in ('id','pointer','scope','nameBytes'))<=0 or row['local'] not in (0,1) or min(row['file'],row['line'])<0:raise ValueError('Invalid parameter identity')
        row['name']=hexrow('VPM_NAME',row['nameBytes'])
        if i>=len(lines):raise ValueError('Missing parameter value')
        a=lines[i].split();i+=1
        if row['kind']=='binary':
            if len(a)!=8 or a[0]!='VPM_BINARY':raise ValueError('Missing binary value')
            value=dict(width=int(a[1]),signed=int(a[2]),sized=int(a[3]),wordBits=int(a[4]),wordCount=int(a[5]),aPointer=pointer(a[6]),bPointer=pointer(a[7]),words=[])
            w=value['wordBits'];n=value['wordCount'];width=value['width']
            if w not in (32,64) or width<0 or value['signed'] not in (0,1) or value['sized'] not in (0,1) or n!=max(1,(width+w-1)//w) or bool(value['aPointer'])!=(width>w) or bool(value['bPointer'])!=(width>w) or n>len(lines)-i:raise ValueError('Invalid binary layout')
            for index in range(n):
                a=lines[i].split();i+=1
                if len(a)!=4 or a[:2]!=['VPM_WORD',str(index)]:raise ValueError('Missing binary storage word')
                pair=[int(v,16) for v in a[2:]]
                if any(not 0<=v<(1<<w) for v in pair):raise ValueError('Binary storage overflow')
                value['words'].append(pair)
        elif row['kind']=='string':
            if len(a)!=3 or a[0]!='VPM_STRING' or pointer(a[1])<=0 or int(a[2])<=0:raise ValueError('Invalid string value')
            value=dict(pointer=pointer(a[1]),bytes=int(a[2]));value['value']=hexrow('VPM_BYTES',value['bytes'])
        elif row['kind']=='real':
            if a!=['VPM_REAL','8']:raise ValueError('Unsupported real representation')
            value=dict(bytes=8,value=hexrow('VPM_BYTES',8))
        else:raise ValueError('Unsupported parameter family')
        row['value']=value;rows.append(row)
    if lines[i:]!=[f'VPM_END {len(rows)}'] or [r['id'] for r in rows]!=sorted({r['id'] for r in rows}) or len({r['pointer'] for r in rows})!=len(rows):raise ValueError('Incomplete/aliased parameter image')
    return dict(tick=tick,rows=rows)


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={};expected=[]
    for r in (1,2):expected += [f'ROUND {r}','REFUSED width','REFUSED missing-owner','REFUSED duplicate-owner',f'RESTORED {r}']
    expected += ['CONTINUE 3 123456789abcdef01234 1.5','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native parameter failure')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid parameter image')
                images[key]=parse(lines[start:i]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Changed parameter continuation/refusal')
    if set(images)!={f'{kind}{r}' for r in (1,2) for kind in ('before','small','wide','signed','sized','real','restored')}:raise ValueError('Missing parameter controls')
    for r in (1,2):
        before=images[f'before{r}']
        if before!=images[f'restored{r}'] or before['tick']!=r*1000 or len(before['rows'])!=4:raise ValueError('Parameter restoration/population differs')
        indexes={bytes.fromhex(p['name']).decode().rstrip('\0'):i for i,p in enumerate(before['rows'])}
        if set(indexes)!={'P','W','R','S'}:raise ValueError('Missing parameter families')
        string=before['rows'][indexes['S']]
        if string['kind']!='string' or string['value']['value']!='41004200':raise ValueError('Embedded-null string lost')
        for kind,target in (('small','P'),('wide','W'),('signed','P'),('sized','P'),('real','R')):
            expected=copy.deepcopy(before);value=expected['rows'][indexes[target]]['value']
            if kind=='small':value['words'][0][0]^=1
            elif kind=='wide':value['words'][70//value['wordBits']][0]^=1<<(70%value['wordBits'])
            elif kind in ('signed','sized'):value[kind]^=1
            else:value['value']=struct.pack('=d',2.5).hex()
            if images[f'{kind}{r}']!=expected:raise ValueError('Wrong isolated parameter payload change')
    return dict(qualified=False,controlsPassed=True,rounds=2,parameters=4,families=['binary','string','real'],embeddedNullStringPreserved=True,originalContinuationExactlyEqual=True,zeroOutputRefusalsPerRound=3,
        scope='Binary raw words, signed/sized flags, string bytes including embedded null and terminator, real representation bytes, and parameter metadata are retained. Five isolated value/flag mutations per round restore exactly; width and missing/duplicate owner faults refuse with negative status and zero output. Native static fixture only; remaining pointer/family/lifecycle and operational board qualification remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_payload.{ext}',out/f'probe.{ext}')
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
