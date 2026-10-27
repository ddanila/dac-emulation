#!/usr/bin/env python3
"""Exercise paired native memory faults across writes, cache creation and continuation."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from memory_metadata import parse
from array_probe import parse as parse_array,validate
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native continuation')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid image framing')
                if key.startswith(('arrays','values')):
                    image=parse_array(lines[start:i]);validate(image)
                else:image=parse(lines[start:i])
                images[key]=image;i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            if r==2:expected.append('INDEXED 5')
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected += [f'FAULT {r} {f} restored' for f in range(5)]
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE 7 5 7','finish']:raise ValueError('Changed fault restoration or HDL continuation')
    for r in (1,2):
        before=images.get(f'before{r}');arrays=images.get(f'arrays{r}')
        if not before or not arrays or before['tick']!=r*1000 or arrays['tick']!=r*1000 or len(before['rows'])!=1 or len(arrays['arrays'])!=1:raise ValueError('Missing native state')
        row=before['rows'][0];array=arrays['arrays'][0]
        if row['array']!=array['key'] or row['scope']!=array['scope']:raise ValueError('Memory/array owner mismatch')
        if len(arrays['ports'])!=1 or arrays['ports'][0]['address']!=r-1:raise ValueError('Missing read-port address transition')
        if row['name']!=b'memory\0'.hex():raise ValueError('Changed memory name')
        expected=copy.deepcopy(before);data=bytearray.fromhex(row['name']);data[0]^=1;expected['rows'][0]['name']=data.hex()
        if images.get(f'changed{r}')!=expected or images.get(f'restored{r}')!=before or images.get(f'values{r}')!=arrays:raise ValueError('Unrelated change or incomplete restoration')
        if bool(array['cache'])!=(r==2) or array['words']!=({1:['1100','0101'],2:['0011','1010']}[r]):raise ValueError('Missing writes or lazy cache transition')
    old=copy.deepcopy(images['arrays1']);new=images['arrays2'];old['tick']=new['tick']
    for k in ('words','cache','cacheParent','cacheWords'):old['arrays'][0][k]=new['arrays'][0][k]
    old['ports'][0]['address']=new['ports'][0]['address']
    names=copy.deepcopy(images['before1']);names['tick']=images['before2']['tick']
    if old!=new or names!=images['before2']:raise ValueError('Unrelated identity changed between rounds')
    if set(images)!={f'{k}{r}' for k in ('before','arrays','changed','restored','values') for r in (1,2)}:raise ValueError('Unexpected images')
    return dict(qualified=False,controlsPassed=True,rounds=2,restoredFaults=10,zeroOutputRefusals=8,isolatedNameChanges=2,wrongFieldRefusals=10,unknownFieldRefusals=2,originalContinuationExactlyEqual=True,
        scope='Five paired native memory faults before and after HDL writes and explicit lazy cache allocation. Direct inventories restore exactly; read-port output and subsequent HDL write match original and disabled runtimes. Static memory lifetime only; this does not qualify later board boundaries or complete transient observation.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/memory_fault_continue.{ext}',out/f'probe.{ext}')
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
